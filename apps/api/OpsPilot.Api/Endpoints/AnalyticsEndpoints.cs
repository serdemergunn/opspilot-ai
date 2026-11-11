using Microsoft.EntityFrameworkCore;
using OpsPilot.Api.Analytics;
using OpsPilot.Api.Data;
using OpsPilot.Api.Tools;

namespace OpsPilot.Api.Endpoints;

/// <summary>Public, read-only endpoints for the dashboard (camelCase JSON, RFC 7807 errors).</summary>
public static class AnalyticsEndpoints
{
    public static void MapAnalyticsEndpoints(this IEndpointRouteBuilder app)
    {
        var api = app.MapGroup("/api");

        api.MapGet("/health", async (OpsPilotDbContext db, CancellationToken ct) =>
            await db.Database.CanConnectAsync(ct)
                ? Results.Ok(new { status = "healthy" })
                : Results.Json(new { status = "unhealthy" }, statusCode: StatusCodes.Status503ServiceUnavailable));

        api.MapGet("/meta", async (OpsPilotDbContext db, PlantClock clock, CancellationToken ct) =>
        {
            var first = await db.ProductionRecords.MinAsync(r => (DateTime?)r.PeriodStartUtc, ct);
            var last = await db.ProductionRecords.MaxAsync(r => (DateTime?)r.PeriodStartUtc, ct);
            return Results.Ok(new
            {
                referenceTimeUtc = clock.NowUtc,
                clockPinned = clock.IsPinned,
                today = clock.Today,
                plantTimeZone = clock.Zone.Id,
                dataset = new
                {
                    firstDate = first is null ? (DateOnly?)null : clock.LocalDateOf(first.Value),
                    lastDate = last is null ? (DateOnly?)null : clock.LocalDateOf(last.Value),
                },
                limits = new { maxRangeDays = ToolArgumentValidator.MaxRangeDays, maxTopN = ToolArgumentValidator.MaxTopN },
            });
        });

        api.MapGet("/lines", async (OpsPilotDbContext db, CancellationToken ct) =>
            Results.Ok(await db.ProductionLines.AsNoTracking().OrderBy(l => l.Code)
                .Select(l => new { l.Code, l.Name, l.Department, l.IsActive }).ToListAsync(ct)));

        var analytics = api.MapGroup("/analytics");
        analytics.MapGet("/production-summary", (HttpRequest r, AnalyticsService s, PlantClock c, CancellationToken ct) =>
            Run(r, c, false, q => s.ProductionSummaryAsync(q, ct)));
        analytics.MapGet("/downtime-by-line", (HttpRequest r, AnalyticsService s, PlantClock c, CancellationToken ct) =>
            Run(r, c, true, q => s.DowntimeByLineAsync(q, ct)));
        analytics.MapGet("/downtime-reasons", (HttpRequest r, AnalyticsService s, PlantClock c, CancellationToken ct) =>
            Run(r, c, true, q => s.DowntimeReasonsAsync(q, ct)));
        analytics.MapGet("/daily-trend", (HttpRequest r, AnalyticsService s, PlantClock c, CancellationToken ct) =>
            Run(r, c, false, q => s.DailyTrendAsync(q, ct)));
    }

    private static async Task<IResult> Run<T>(
        HttpRequest request, PlantClock clock, bool downtimeOptions, Func<AnalyticsQuery, Task<AnalyticsResult<T>>> execute)
    {
        var errors = new Dictionary<string, string[]>();
        var q = request.Query;
        var args = new ToolArguments
        {
            StartDate = q["startDate"],
            EndDate = q["endDate"],
            LineCodes = q["lineCodes"].Count == 0
                ? null
                : q["lineCodes"].SelectMany(v => (v ?? "").Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries)).ToList(),
            IncludePlanned = ParseOptional<bool>(q["includePlanned"], bool.TryParse, "includePlanned", errors),
            TopN = ParseOptional<int>(q["topN"], int.TryParse, "topN", errors),
        };
        if (errors.Count > 0) return Results.ValidationProblem(errors);
        try
        {
            var query = ToolArgumentValidator.Validate(args, downtimeOptions, clock.Today);
            var result = await execute(query);
            return Results.Ok(new { data = result.Data, meta = result.Meta });
        }
        catch (ToolValidationException ex)
        {
            return Results.ValidationProblem(ex.Errors.ToDictionary(kv => ToCamel(kv.Key), kv => kv.Value));
        }
    }

    private delegate bool TryParse<T>(string? s, out T value);

    private static T? ParseOptional<T>(string? raw, TryParse<T> parse, string name, Dictionary<string, string[]> errors)
        where T : struct
    {
        if (string.IsNullOrEmpty(raw)) return null;
        if (parse(raw, out var v)) return v;
        errors[name] = [$"{name} has an invalid value."];
        return null;
    }

    private static string ToCamel(string snake)
    {
        var parts = snake.Split('_');
        return parts[0] + string.Concat(parts.Skip(1).Select(p => p.Length == 0 ? p : char.ToUpperInvariant(p[0]) + p[1..]));
    }
}
