using Microsoft.Data.SqlClient;
using Microsoft.EntityFrameworkCore;

namespace OpsPilot.Api.Data;

/// <summary>
/// Startup step that uses the privileged "Migrator" connection to apply migrations, seed the synthetic
/// dataset when the database is empty, and provision the read-only login used by every analytics query.
/// The privileged connection is never used to serve requests.
/// </summary>
public sealed class DatabaseInitializer(IConfiguration config, IHostEnvironment env, ILogger<DatabaseInitializer> logger)
    : IHostedService
{
    public async Task StartAsync(CancellationToken ct)
    {
        var migratorCs = config.GetConnectionString("Migrator");
        if (string.IsNullOrWhiteSpace(migratorCs))
        {
            logger.LogInformation("No Migrator connection string configured; skipping database initialization");
            return;
        }

        var options = new DbContextOptionsBuilder<OpsPilotDbContext>().UseSqlServer(migratorCs).Options;
        await using var db = new OpsPilotDbContext(options);
        db.Database.SetCommandTimeout(TimeSpan.FromMinutes(2));

        await RetryAsync(() => db.Database.MigrateAsync(ct), ct);

        if (!await db.ProductionLines.AnyAsync(ct))
        {
            var csvDir = Path.GetFullPath(config["Seed:CsvDirectory"]
                ?? throw new InvalidOperationException("Seed:CsvDirectory is required to seed an empty database."),
                env.ContentRootPath);
            logger.LogInformation("Seeding synthetic dataset from {CsvDirectory}", csvDir);
            await new CsvSeeder(db, csvDir).SeedAsync(ct);
        }

        var readerCs = config.GetConnectionString("Reader");
        if (!string.IsNullOrWhiteSpace(readerCs))
        {
            var reader = new SqlConnectionStringBuilder(readerCs);
            await EnsureReadOnlyUserAsync(db, reader.UserID, reader.Password, ct);
            logger.LogInformation("Read-only database user {Login} is provisioned", reader.UserID);
        }
    }

    public Task StopAsync(CancellationToken ct) => Task.CompletedTask;

    private static Task EnsureReadOnlyUserAsync(OpsPilotDbContext db, string login, string password, CancellationToken ct)
    {
        // Identifiers cannot be parameters in DDL, so values are passed as parameters and quoted with QUOTENAME
        // inside dynamic SQL. No caller-provided text is concatenated into the command.
        // QUOTENAME returns NULL above 128 characters, which would make EXEC(@q) a silent no-op.
        if (login.Length is 0 or > 128 || password.Length is 0 or > 128)
            throw new InvalidOperationException("The reader login and password must be 1-128 characters.");
        const string sql = """
            DECLARE @q nvarchar(max);
            IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = @login)
                SET @q = N'CREATE LOGIN ' + QUOTENAME(@login) + N' WITH PASSWORD = ' + QUOTENAME(@password, '''');
            ELSE
                SET @q = N'ALTER LOGIN ' + QUOTENAME(@login) + N' WITH PASSWORD = ' + QUOTENAME(@password, '''');
            EXEC (@q);
            IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = @login)
            BEGIN
                SET @q = N'CREATE USER ' + QUOTENAME(@login) + N' FOR LOGIN ' + QUOTENAME(@login);
                EXEC (@q);
            END
            IF IS_ROLEMEMBER('db_datareader', @login) = 0
            BEGIN
                SET @q = N'ALTER ROLE db_datareader ADD MEMBER ' + QUOTENAME(@login);
                EXEC (@q);
            END
            """;
        return db.Database.ExecuteSqlRawAsync(sql,
            [new SqlParameter("@login", login), new SqlParameter("@password", password)], ct);
    }

    private async Task RetryAsync(Func<Task> action, CancellationToken ct)
    {
        for (var attempt = 1; ; attempt++)
        {
            try
            {
                await action();
                return;
            }
            catch (SqlException ex) when (attempt < 30)
            {
                logger.LogWarning("Database not ready (attempt {Attempt}): {Message}", attempt, ex.Message);
                await Task.Delay(TimeSpan.FromSeconds(2), ct);
            }
        }
    }
}
