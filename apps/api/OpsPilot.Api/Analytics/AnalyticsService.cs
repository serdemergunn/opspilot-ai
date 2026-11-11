using System.Diagnostics;
using Microsoft.EntityFrameworkCore;
using OpsPilot.Api.Data;
using OpsPilot.Api.Tools;

namespace OpsPilot.Api.Analytics;

public sealed record QueryMeta(
    DateTime WindowStartUtc, DateTime WindowEndUtc, int RowCount, bool Truncated, long QueryMs, string Source,
    string MetricDefinitionsVersion);

public sealed record AnalyticsResult<T>(T Data, QueryMeta Meta);

/// <summary>
/// Read-only analytics over the operational database. Queries are fixed LINQ expressions (parameterized SQL);
/// all arithmetic is delegated to <see cref="MetricCalculator"/>.
/// </summary>
public sealed class AnalyticsService(OpsPilotDbContext db, PlantClock clock)
{
    public async Task<IReadOnlyList<LineInfo>> GetActiveLinesAsync(CancellationToken ct) =>
        await db.ProductionLines.AsNoTracking().Where(l => l.IsActive).OrderBy(l => l.Code)
            .Select(l => new LineInfo(l.Id, l.Code, l.Name)).ToListAsync(ct);

    public async Task<AnalyticsResult<ProductionSummaryResult>> ProductionSummaryAsync(AnalyticsQuery q, CancellationToken ct)
    {
        var sw = Stopwatch.StartNew();
        var (lines, w) = await ResolveAsync(q, ct);
        var production = await LoadProductionAsync(lines, w, ct);
        var downtime = await LoadDowntimeAsync(lines, w, ct);
        var data = MetricCalculator.ProductionSummary(lines, production, downtime, w);
        return new(data, Meta(w, production.Count + downtime.Count, false, sw, "ProductionRecords,DowntimeEvents"));
    }

    public async Task<AnalyticsResult<DowntimeByLineResult>> DowntimeByLineAsync(AnalyticsQuery q, CancellationToken ct)
    {
        var sw = Stopwatch.StartNew();
        var (lines, w) = await ResolveAsync(q, ct);
        var downtime = await LoadDowntimeAsync(lines, w, ct);
        var data = MetricCalculator.DowntimeByLine(lines, await LoadReasonsAsync(ct), downtime, w, q.IncludePlanned, q.TopN);
        return new(data, Meta(w, downtime.Count, data.OmittedCount > 0, sw, "DowntimeEvents"));
    }

    public async Task<AnalyticsResult<DowntimeReasonsResult>> DowntimeReasonsAsync(AnalyticsQuery q, CancellationToken ct)
    {
        var sw = Stopwatch.StartNew();
        var (lines, w) = await ResolveAsync(q, ct);
        var downtime = await LoadDowntimeAsync(lines, w, ct);
        var data = MetricCalculator.DowntimeReasons(lines, await LoadReasonsAsync(ct), downtime, w, q.IncludePlanned, q.TopN);
        return new(data, Meta(w, downtime.Count, data.OmittedCount > 0, sw, "DowntimeEvents,DowntimeReasons"));
    }

    public async Task<AnalyticsResult<DailyTrendResult>> DailyTrendAsync(AnalyticsQuery q, CancellationToken ct)
    {
        var sw = Stopwatch.StartNew();
        var (lines, w) = await ResolveAsync(q, ct);
        var production = await LoadProductionAsync(lines, w, ct);
        var downtime = await LoadDowntimeAsync(lines, w, ct);
        var days = new List<(DateOnly, TimeWindow)>();
        for (var d = q.StartDate; d <= q.EndDate; d = d.AddDays(1)) days.Add((d, clock.ToUtcWindow(d, d)));
        var data = MetricCalculator.DailyTrend(lines, production, downtime, days);
        return new(data, Meta(w, production.Count + downtime.Count, false, sw, "ProductionRecords,DowntimeEvents"));
    }

    private async Task<(IReadOnlyList<LineInfo> Lines, TimeWindow Window)> ResolveAsync(AnalyticsQuery q, CancellationToken ct)
    {
        var all = await db.ProductionLines.AsNoTracking().OrderBy(l => l.Code)
            .Select(l => new { l.Id, l.Code, l.Name, l.IsActive }).ToListAsync(ct);
        if (q.LineCodes is { } codes)
        {
            var unknown = codes.Except(all.Select(l => l.Code), StringComparer.Ordinal).ToList();
            if (unknown.Count > 0)
            {
                throw new ToolValidationException(new Dictionary<string, string[]>
                {
                    ["line_codes"] = [$"Unknown line codes: {string.Join(", ", unknown)}. Known: {string.Join(", ", all.Select(l => l.Code))}."],
                });
            }
        }
        var lines = all.Where(l => l.IsActive && (q.LineCodes is null || q.LineCodes.Contains(l.Code)))
            .Select(l => new LineInfo(l.Id, l.Code, l.Name)).ToList();
        return (lines, clock.ToUtcWindow(q.StartDate, q.EndDate));
    }

    private async Task<List<ProductionRow>> LoadProductionAsync(IReadOnlyList<LineInfo> lines, TimeWindow w, CancellationToken ct)
    {
        var ids = lines.Select(l => l.Id).ToList();
        return await db.ProductionRecords.AsNoTracking()
            .Where(r => ids.Contains(r.LineId) && r.PeriodStartUtc >= w.StartUtc && r.PeriodStartUtc < w.EndUtc)
            .Select(r => new ProductionRow(r.LineId, r.PeriodStartUtc, r.PlannedQuantity, r.ProducedQuantity, r.DefectiveQuantity))
            .ToListAsync(ct);
    }

    private async Task<List<DowntimeRow>> LoadDowntimeAsync(IReadOnlyList<LineInfo> lines, TimeWindow w, CancellationToken ct)
    {
        var ids = lines.Select(l => l.Id).ToList();
        return await db.DowntimeEvents.AsNoTracking()
            .Where(e => ids.Contains(e.LineId) && e.StartTimeUtc < w.EndUtc && e.EndTimeUtc > w.StartUtc)
            .Select(e => new DowntimeRow(e.LineId, e.StartTimeUtc, e.EndTimeUtc, e.ReasonCode))
            .ToListAsync(ct);
    }

    private async Task<IReadOnlyDictionary<string, ReasonInfo>> LoadReasonsAsync(CancellationToken ct) =>
        await db.DowntimeReasons.AsNoTracking()
            .ToDictionaryAsync(r => r.Code, r => new ReasonInfo(r.Code, r.Name, r.Category, r.IsPlanned), ct);

    private static QueryMeta Meta(TimeWindow w, int rows, bool truncated, Stopwatch sw, string tables) =>
        new(w.StartUtc, w.EndUtc, rows, truncated, sw.ElapsedMilliseconds, $"sqlserver:{tables}", MetricCalculator.DefinitionsVersion);
}
