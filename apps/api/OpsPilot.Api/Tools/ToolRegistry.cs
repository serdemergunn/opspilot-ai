using System.Text.Json.Nodes;
using OpsPilot.Api.Analytics;

namespace OpsPilot.Api.Tools;

public sealed record ToolDefinition(
    string Name,
    string Description,
    bool SupportsDowntimeOptions,
    Func<AnalyticsService, AnalyticsQuery, CancellationToken, Task<AnalyticsResult<object>>> Execute)
{
    public JsonObject InputSchema => ToolSchemas.Build(SupportsDowntimeOptions);
}

/// <summary>
/// The allowlist. A tool exists only if it is listed here; there is no other path from the agent to data.
/// Every tool is read-only and bounded by <see cref="ToolArgumentValidator"/>.
/// </summary>
public static class ToolRegistry
{
    public static readonly IReadOnlyDictionary<string, ToolDefinition> Tools = new[]
    {
        new ToolDefinition("get_production_summary",
            "Totals of planned, produced and defective units, attainment, defect rate and downtime for a date range, overall and per line. Read-only.",
            false, async (s, q, ct) => Box(await s.ProductionSummaryAsync(q, ct))),
        new ToolDefinition("get_downtime_by_line",
            "Downtime minutes, event count and share of total per production line for a date range, sorted by downtime descending. Read-only.",
            true, async (s, q, ct) => Box(await s.DowntimeByLineAsync(q, ct))),
        new ToolDefinition("get_downtime_reasons",
            "Downtime grouped by reason code with minutes, event count and share of total for a date range, optionally filtered by line. Read-only.",
            true, async (s, q, ct) => Box(await s.DowntimeReasonsAsync(q, ct))),
        new ToolDefinition("get_daily_production_trend",
            "Per-day planned, produced and defective units, attainment, defect rate and downtime for a date range. Read-only.",
            false, async (s, q, ct) => Box(await s.DailyTrendAsync(q, ct))),
    }.ToDictionary(t => t.Name, StringComparer.Ordinal);

    private static AnalyticsResult<object> Box<T>(AnalyticsResult<T> r) where T : notnull => new(r.Data, r.Meta);
}

internal static class ToolSchemas
{
    public static JsonObject Build(bool downtimeOptions)
    {
        var properties = new JsonObject
        {
            ["start_date"] = new JsonObject { ["type"] = "string", ["format"] = "date", ["description"] = "Inclusive, plant-local (YYYY-MM-DD)." },
            ["end_date"] = new JsonObject { ["type"] = "string", ["format"] = "date", ["description"] = "Inclusive, plant-local (YYYY-MM-DD)." },
            ["line_codes"] = new JsonObject
            {
                ["type"] = "array",
                ["items"] = new JsonObject { ["type"] = "string", ["pattern"] = @"^L\d{2}$" },
                ["minItems"] = 1, ["maxItems"] = ToolArgumentValidator.MaxLineCodes, ["uniqueItems"] = true,
                ["description"] = "Optional filter, e.g. [\"L01\", \"L04\"]. Omit for all active lines.",
            },
        };
        if (downtimeOptions)
        {
            properties["include_planned"] = new JsonObject
            {
                ["type"] = "boolean", ["default"] = true,
                ["description"] = "Include planned downtime (changeovers, planned maintenance).",
            };
            properties["top_n"] = new JsonObject
            {
                ["type"] = "integer", ["minimum"] = 1, ["maximum"] = ToolArgumentValidator.MaxTopN,
                ["default"] = ToolArgumentValidator.DefaultTopN,
            };
        }
        return new JsonObject
        {
            ["type"] = "object",
            ["additionalProperties"] = false,
            ["required"] = new JsonArray("start_date", "end_date"),
            ["properties"] = properties,
        };
    }
}
