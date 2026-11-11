using System.Net;
using System.Threading.RateLimiting;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
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
builder.Services.AddExceptionHandler<DatabaseUnavailableHandler>();

// Behind the nginx container every request arrives from the proxy's address, which would make the chat rate
// limit global. When enabled, trust X-Forwarded-For (one hop) from private networks only; nginx overwrites the
// header with the real client address, so clients cannot choose their own bucket.
if (builder.Configuration.GetValue<bool>("OpsPilot:ForwardedHeaders:Enabled"))
{
    builder.Services.Configure<ForwardedHeadersOptions>(o =>
    {
        o.ForwardedHeaders = ForwardedHeaders.XForwardedFor;
        o.ForwardLimit = 1;
        o.KnownProxies.Clear();
        o.KnownNetworks.Clear();
        foreach (var cidr in new[] { "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16" })
        {
            var parts = cidr.Split('/');
            o.KnownNetworks.Add(new Microsoft.AspNetCore.HttpOverrides.IPNetwork(IPAddress.Parse(parts[0]), int.Parse(parts[1])));
        }
    });
}

// Request-serving context uses the read-only login. Read lazily so test hosts can override configuration.
builder.Services.AddDbContext<OpsPilotDbContext>((sp, o) => o
    .UseSqlServer(sp.GetRequiredService<IConfiguration>().GetConnectionString("Reader")
        ?? throw new InvalidOperationException("ConnectionStrings:Reader is required."))
    .UseQueryTrackingBehavior(QueryTrackingBehavior.NoTracking));
builder.Services.AddScoped<AnalyticsService>();

// Migrate, seed and provision the read-only login before the server starts accepting requests.
builder.Services.AddHostedService<DatabaseInitializer>();

// The agent sits behind the API: the browser never talks to the AI service directly (ADR 0002).
builder.Services.AddHttpClient(ChatEndpoints.HttpClientName, (sp, c) =>
{
    var ai = sp.GetRequiredService<IOptions<OpsPilotOptions>>().Value.AiService;
    c.BaseAddress = new Uri(ai.BaseUrl);
    c.Timeout = TimeSpan.FromSeconds(ai.TimeoutSeconds);
});
builder.Services.AddRateLimiter(o =>
{
    o.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
    o.AddPolicy(ChatEndpoints.RateLimitPolicy, ctx => RateLimitPartition.GetFixedWindowLimiter(
        ctx.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        _ => new FixedWindowRateLimiterOptions
        {
            PermitLimit = ctx.RequestServices.GetRequiredService<IOptions<OpsPilotOptions>>().Value.AiService.RequestsPerMinute,
            Window = TimeSpan.FromMinutes(1),
            QueueLimit = 0,
        }));
});

builder.Services.AddCors(o => o.AddDefaultPolicy(p => p
    .WithOrigins(builder.Configuration.GetSection("Cors:AllowedOrigins").Get<string[]>() ?? [])
    .WithMethods("GET", "POST")
    .AllowAnyHeader()));

var app = builder.Build();

if (app.Configuration.GetValue<bool>("OpsPilot:ForwardedHeaders:Enabled")) app.UseForwardedHeaders();
app.UseExceptionHandler();
app.UseStatusCodePages();
app.UseCors();
app.UseRateLimiter();

app.MapAnalyticsEndpoints();
app.MapToolEndpoints();
app.MapChatEndpoints();

app.Run();

public partial class Program;
