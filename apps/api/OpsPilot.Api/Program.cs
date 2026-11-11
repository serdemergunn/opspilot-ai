using Microsoft.EntityFrameworkCore;
using OpsPilot.Api.Analytics;
using OpsPilot.Api.Data;
using OpsPilot.Api.Endpoints;

var builder = WebApplication.CreateBuilder(args);

builder.Logging.ClearProviders();
builder.Logging.AddJsonConsole(o =>
{
    o.IncludeScopes = true;
    o.UseUtcTimestamp = true;
    o.TimestampFormat = "yyyy-MM-ddTHH:mm:ss.fffZ";
});

builder.Services.AddOptions<OpsPilotOptions>().BindConfiguration("OpsPilot");
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddSingleton<PlantClock>();
builder.Services.AddProblemDetails();

// Request-serving context uses the read-only login. Read lazily so test hosts can override configuration.
builder.Services.AddDbContext<OpsPilotDbContext>((sp, o) => o
    .UseSqlServer(sp.GetRequiredService<IConfiguration>().GetConnectionString("Reader")
        ?? throw new InvalidOperationException("ConnectionStrings:Reader is required."))
    .UseQueryTrackingBehavior(QueryTrackingBehavior.NoTracking));
builder.Services.AddScoped<AnalyticsService>();

// Migrate, seed and provision the read-only login before the server starts accepting requests.
builder.Services.AddHostedService<DatabaseInitializer>();

builder.Services.AddCors(o => o.AddDefaultPolicy(p => p
    .WithOrigins(builder.Configuration.GetSection("Cors:AllowedOrigins").Get<string[]>() ?? [])
    .WithMethods("GET", "POST")
    .AllowAnyHeader()));

var app = builder.Build();

app.UseExceptionHandler();
app.UseStatusCodePages();
app.UseCors();

app.MapAnalyticsEndpoints();
app.MapToolEndpoints();

app.Run();

public partial class Program;
