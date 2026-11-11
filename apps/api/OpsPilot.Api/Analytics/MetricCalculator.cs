namespace OpsPilot.Api.Analytics;

// Pure implementation of docs/architecture/metric-definitions.md (version 1).
// No I/O: the caller loads rows, this class does all arithmetic, so every formula is unit-testable.

public sealed record LineInfo(int Id, string Code, string Name);
public sealed record ReasonInfo(string Code, string Name, string Category, bool IsPlanned);
public sealed record ProductionRow(int LineId, DateTime PeriodStartUtc, int Planned, int Produced, int Defective);
public sealed record DowntimeRow(int LineId, DateTime StartUtc, DateTime EndUtc, string ReasonCode);

public sealed record ProductionMetrics(
    long PlannedQuantity, long ProducedQuantity, long DefectiveQuantity, long GoodQuantity,
    decimal? AttainmentPct, decimal? DefectRatePct, long DowntimeMinutes, decimal DowntimeHours, int RecordCount);

public sealed record LineProductionMetrics(
    string LineCode, string LineName,
    long PlannedQuantity, long ProducedQuantity, long DefectiveQuantity, long GoodQuantity,
    decimal? AttainmentPct, decimal? DefectRatePct, long DowntimeMinutes, decimal DowntimeHours, int RecordCount);

public sealed record ProductionSummaryResult(ProductionMetrics Totals, IReadOnlyList<LineProductionMetrics> ByLine);

public sealed record LineDowntime(
    string LineCode, string LineName, long DowntimeMinutes, decimal DowntimeHours, int EventCount, decimal? SharePct);

public sealed record DowntimeByLineResult(long TotalDowntimeMinutes, IReadOnlyList<LineDowntime> Items, int OmittedCount);

public sealed record ReasonDowntime(
    string ReasonCode, string ReasonName, string Category, bool IsPlanned,
    long DowntimeMinutes, decimal DowntimeHours, int EventCount, decimal? SharePct);

public sealed record DowntimeReasonsResult(long TotalDowntimeMinutes, IReadOnlyList<ReasonDowntime> Items, int OmittedCount);

public sealed record DailyProductionPoint(
    DateOnly Date, long PlannedQuantity, long ProducedQuantity, long DefectiveQuantity, long GoodQuantity,
    decimal? AttainmentPct, decimal? DefectRatePct, long DowntimeMinutes);

public sealed record DailyTrendResult(IReadOnlyList<DailyProductionPoint> Items);

public static class MetricCalculator
{
    public const string DefinitionsVersion = "1";

    /// <summary>1 decimal place, midpoint away from zero (never banker's rounding).</summary>
    public static decimal Round1(decimal value) => Math.Round(value, 1, MidpointRounding.AwayFromZero);

    public static decimal? Pct(long numerator, long denominator) =>
        denominator == 0 ? null : Round1(numerator * 100m / denominator);

    public static decimal Hours(long minutes) => Round1(minutes / 60m);

    public static long ClippedMinutes(DateTime start, DateTime end, TimeWindow w)
    {
        var from = start > w.StartUtc ? start : w.StartUtc;
        var to = end < w.EndUtc ? end : w.EndUtc;
        return to <= from ? 0 : (to - from).Ticks / TimeSpan.TicksPerMinute;
    }

    public static ProductionSummaryResult ProductionSummary(
        IReadOnlyList<LineInfo> lines, IEnumerable<ProductionRow> production, IEnumerable<DowntimeRow> downtime, TimeWindow w)
    {
        var acc = lines.ToDictionary(l => l.Id, _ => new Accumulator());
        foreach (var r in production)
        {
            if (!acc.TryGetValue(r.LineId, out var a) || r.PeriodStartUtc < w.StartUtc || r.PeriodStartUtc >= w.EndUtc) continue;
            a.Planned += r.Planned;
            a.Produced += r.Produced;
            a.Defective += r.Defective;
            a.Records++;
        }
        foreach (var d in downtime)
        {
            if (acc.TryGetValue(d.LineId, out var a)) a.Downtime += ClippedMinutes(d.StartUtc, d.EndUtc, w);
        }

        var total = new Accumulator();
        foreach (var a in acc.Values) total.Add(a);
        var t = Shape(total);
        return new ProductionSummaryResult(t, lines.Select(l =>
        {
            var m = Shape(acc[l.Id]);
            return new LineProductionMetrics(l.Code, l.Name, m.PlannedQuantity, m.ProducedQuantity, m.DefectiveQuantity,
                m.GoodQuantity, m.AttainmentPct, m.DefectRatePct, m.DowntimeMinutes, m.DowntimeHours, m.RecordCount);
        }).ToList());
    }

    public static DowntimeByLineResult DowntimeByLine(
        IReadOnlyList<LineInfo> lines, IReadOnlyDictionary<string, ReasonInfo> reasons, IEnumerable<DowntimeRow> downtime,
        TimeWindow w, bool includePlanned, int topN)
    {
        var minutes = lines.ToDictionary(l => l.Id, _ => 0L);
        var counts = lines.ToDictionary(l => l.Id, _ => 0);
        foreach (var (row, m) in Clip(reasons, downtime, w, includePlanned))
        {
            if (!minutes.ContainsKey(row.LineId)) continue;
            minutes[row.LineId] += m;
            counts[row.LineId]++;
        }
        var total = minutes.Values.Sum();
        var items = lines
            .Select(l => new LineDowntime(l.Code, l.Name, minutes[l.Id], Hours(minutes[l.Id]), counts[l.Id], Pct(minutes[l.Id], total)))
            .OrderByDescending(i => i.DowntimeMinutes).ThenBy(i => i.LineCode, StringComparer.Ordinal)
            .ToList();
        return new DowntimeByLineResult(total, items.Take(topN).ToList(), Math.Max(0, items.Count - topN));
    }

    public static DowntimeReasonsResult DowntimeReasons(
        IReadOnlyList<LineInfo> lines, IReadOnlyDictionary<string, ReasonInfo> reasons, IEnumerable<DowntimeRow> downtime,
        TimeWindow w, bool includePlanned, int topN)
    {
        var lineIds = lines.Select(l => l.Id).ToHashSet();
        var minutes = new Dictionary<string, long>();
        var counts = new Dictionary<string, int>();
        foreach (var (row, m) in Clip(reasons, downtime, w, includePlanned))
        {
            if (!lineIds.Contains(row.LineId)) continue;
            minutes[row.ReasonCode] = minutes.GetValueOrDefault(row.ReasonCode) + m;
            counts[row.ReasonCode] = counts.GetValueOrDefault(row.ReasonCode) + 1;
        }
        var total = minutes.Values.Sum();
        var items = minutes
            .Select(kv =>
            {
                var r = reasons[kv.Key];
                return new ReasonDowntime(r.Code, r.Name, r.Category, r.IsPlanned, kv.Value, Hours(kv.Value), counts[kv.Key],
                    Pct(kv.Value, total));
            })
            .OrderByDescending(i => i.DowntimeMinutes).ThenBy(i => i.ReasonCode, StringComparer.Ordinal)
            .ToList();
        return new DowntimeReasonsResult(total, items.Take(topN).ToList(), Math.Max(0, items.Count - topN));
    }

    /// <summary>One point per plant-local day; <paramref name="days"/> supplies each day's UTC window.</summary>
    public static DailyTrendResult DailyTrend(
        IReadOnlyList<LineInfo> lines, IEnumerable<ProductionRow> production, IEnumerable<DowntimeRow> downtime,
        IReadOnlyList<(DateOnly Date, TimeWindow Window)> days)
    {
        var lineIds = lines.Select(l => l.Id).ToHashSet();
        var prod = production.Where(p => lineIds.Contains(p.LineId)).ToList();
        var down = downtime.Where(d => lineIds.Contains(d.LineId)).ToList();
        return new DailyTrendResult(days.Select(day =>
        {
            var a = new Accumulator();
            foreach (var p in prod.Where(p => p.PeriodStartUtc >= day.Window.StartUtc && p.PeriodStartUtc < day.Window.EndUtc))
            {
                a.Planned += p.Planned;
                a.Produced += p.Produced;
                a.Defective += p.Defective;
            }
            foreach (var d in down) a.Downtime += ClippedMinutes(d.StartUtc, d.EndUtc, day.Window);
            return new DailyProductionPoint(day.Date, a.Planned, a.Produced, a.Defective, a.Produced - a.Defective,
                Pct(a.Produced, a.Planned), Pct(a.Defective, a.Produced), a.Downtime);
        }).ToList());
    }

    private static IEnumerable<(DowntimeRow Row, long Minutes)> Clip(
        IReadOnlyDictionary<string, ReasonInfo> reasons, IEnumerable<DowntimeRow> downtime, TimeWindow w, bool includePlanned)
    {
        foreach (var d in downtime)
        {
            if (!includePlanned && reasons[d.ReasonCode].IsPlanned) continue;
            var m = ClippedMinutes(d.StartUtc, d.EndUtc, w);
            if (m > 0) yield return (d, m);
        }
    }

    private static ProductionMetrics Shape(Accumulator a) => new(
        a.Planned, a.Produced, a.Defective, a.Produced - a.Defective,
        Pct(a.Produced, a.Planned), Pct(a.Defective, a.Produced), a.Downtime, Hours(a.Downtime), a.Records);

    private sealed class Accumulator
    {
        public long Planned, Produced, Defective, Downtime;
        public int Records;

        public void Add(Accumulator o)
        {
            Planned += o.Planned; Produced += o.Produced; Defective += o.Defective; Downtime += o.Downtime; Records += o.Records;
        }
    }
}
