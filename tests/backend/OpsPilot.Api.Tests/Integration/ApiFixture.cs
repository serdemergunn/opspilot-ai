using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Data.SqlClient;
using OpsPilot.Api.Endpoints;
using Testcontainers.MsSql;

namespace OpsPilot.Api.Tests.Integration;

/// <summary>
/// Starts a real SQL Server in Docker and the real API host on top of it. The host's startup path
/// (migrations, CSV seeding, read-only login provisioning) is exercised exactly as in production.
/// </summary>
public sealed class ApiFixture : IAsyncLifetime
{
    public const string ServiceKey = "test-service-key";
    private const string ReaderPassword = "Reader-Passw0rd!Test";

    private readonly MsSqlContainer _sql = new MsSqlBuilder("mcr.microsoft.com/mssql/server:2022-latest").Build();

    public WebApplicationFactory<Program> Factory { get; private set; } = null!;
    public string ReaderConnectionString { get; private set; } = "";

    public static string RepoRoot { get; } = FindRepoRoot();

    public async Task InitializeAsync()
    {
        await _sql.StartAsync();
        var migrator = new SqlConnectionStringBuilder(_sql.GetConnectionString()) { InitialCatalog = "OpsPilot" };
        ReaderConnectionString = new SqlConnectionStringBuilder(migrator.ConnectionString)
        {
            UserID = "opspilot_reader", Password = ReaderPassword,
        }.ConnectionString;

        Factory = new WebApplicationFactory<Program>().WithWebHostBuilder(b =>
        {
            b.UseSetting("ConnectionStrings:Migrator", migrator.ConnectionString);
            b.UseSetting("ConnectionStrings:Reader", ReaderConnectionString);
            b.UseSetting("Seed:CsvDirectory", Path.Combine(RepoRoot, "sample-data", "csv"));
            b.UseSetting("OpsPilot:Clock:ReferenceTimeUtc", "2026-11-11T00:00:00Z");
            b.UseSetting("OpsPilot:Plant:TimeZone", "UTC");
            b.UseSetting("OpsPilot:Tools:ServiceKey", ServiceKey);
        });
        _ = Factory.Server; // starts the host, which runs the database initializer
    }

    public HttpClient CreateClient(bool withServiceKey = false)
    {
        var client = Factory.CreateClient();
        if (withServiceKey) client.DefaultRequestHeaders.Add(ToolEndpoints.ServiceKeyHeader, ServiceKey);
        return client;
    }

    public async Task DisposeAsync()
    {
        if (Factory is not null) await Factory.DisposeAsync();
        await _sql.DisposeAsync();
    }

    private static string FindRepoRoot()
    {
        for (var dir = new DirectoryInfo(AppContext.BaseDirectory); dir is not null; dir = dir.Parent)
        {
            if (File.Exists(Path.Combine(dir.FullName, "OpsPilot.sln"))) return dir.FullName;
        }
        throw new InvalidOperationException("Could not locate the repository root (OpsPilot.sln).");
    }
}

[CollectionDefinition(Name)]
public sealed class ApiCollection : ICollectionFixture<ApiFixture>
{
    public const string Name = "api";
}
