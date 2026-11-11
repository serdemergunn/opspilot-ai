using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace OpsPilot.Api.Data;

/// <summary>Used only by `dotnet ef` to build the model for migrations; never connects.</summary>
public sealed class DesignTimeDbContextFactory : IDesignTimeDbContextFactory<OpsPilotDbContext>
{
    public OpsPilotDbContext CreateDbContext(string[] args) =>
        new(new DbContextOptionsBuilder<OpsPilotDbContext>()
            .UseSqlServer("Server=localhost;Database=OpsPilot;Integrated Security=false;TrustServerCertificate=True").Options);
}
