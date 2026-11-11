using OpsPilot.Api.Analytics;

namespace OpsPilot.Api.Tests.Unit;

// Same hand-computed fixture as tests/data/test_reference_metrics.py, so both implementations are pinned
// to identical expectations independently of the database.
public class MetricCalculatorTests
{
    private static DateTime Utc(int y, int mo, int d, int h = 0, int mi = 0) => new(y, mo, d, h, mi, 0, DateTimeKind.Utc);

    private static readonly LineInfo L01 = new(1, "L01", "Line 01");
    private static readonly LineInfo L02 = new(2, "L02", "Line 02");
    private static readonly IReadOnlyList<LineInfo> ActiveLines = [L01, L02]; // L03 (id 3) is inactive

    private static readonly IReadOnlyDictionary<string, ReasonInfo> Reasons = new Dictionary<string, ReasonInfo>
    {
        ["MECH_FAILURE"] = new("MECH_FAILURE", "Mechanical failure", "Equipment", false),
        ["CHANGEOVER"] = new("CHANGEOVER", "Product changeover", "Planned", true),
    };

    private static readonly ProductionRow[] Production =
    [
        new(1, Utc(2026, 1, 2, 0), 100, 80, 3),
        new(1, Utc(2026, 1, 2, 1), 100, 90, 0),
        new(2, Utc(2026, 1, 2, 0), 50, 0, 0),
        new(1, Utc(2026, 1, 3, 0), 100, 100, 1),
    ];

    private static readonly DowntimeRow[] Downtime =
    [
        new(1, Utc(2026, 1, 1, 23, 30), Utc(2026, 1, 2, 0, 45), "MECH_FAILURE"), // 30 on 01-01, 45 on 01-02
        new(1, Utc(2026, 1, 2, 6), Utc(2026, 1, 2, 6, 30), "CHANGEOVER"),
        new(2, Utc(2026, 1, 2, 10), Utc(2026, 1, 2, 10, 5), "MECH_FAILURE"),
        new(3, Utc(2026, 1, 2, 1), Utc(2026, 1, 2, 2), "MECH_FAILURE"), // inactive line
        new(2, Utc(2026, 1, 1, 22), Utc(2026, 1, 2, 0), "MECH_FAILURE"), // zero overlap with 01-02
    ];

    private static TimeWindow Day(int d) => new(Utc(2026, 1, d), Utc(2026, 1, d + 1));

    [Theory]
    [InlineData(1, 16, 6.3)]   // 6.25 -> 6.3 (banker's rounding would give 6.2)
    [InlineData(49, 400, 12.3)] // 12.25 -> 12.3
    [InlineData(1, 8, 12.5)]
    public void Pct_rounds_half_away_from_zero(long n, long d, double expected) =>
        Assert.Equal((decimal)expected, MetricCalculator.Pct(n, d));

    [Fact]
    public void Hours_rounds_half_away_from_zero()
    {
        Assert.Equal(0.2m, MetricCalculator.Hours(9));  // 0.15
        Assert.Equal(0.3m, MetricCalculator.Hours(15)); // 0.25
    }

    [Fact]
    public void Pct_with_zero_denominator_is_null() => Assert.Null(MetricCalculator.Pct(5, 0));

    [Fact]
    public void Downtime_by_line_clips_to_window_and_counts_overlapping_events()
    {
        var r = MetricCalculator.DowntimeByLine(ActiveLines, Reasons, Downtime, Day(2), includePlanned: true, topN: 10);
        Assert.Equal(80, r.TotalDowntimeMinutes);
        Assert.Equal([("L01", 75L, 2, 93.8m), ("L02", 5L, 1, 6.3m)],
            r.Items.Select(i => (i.LineCode, i.DowntimeMinutes, i.EventCount, i.SharePct!.Value)));
        Assert.Equal(1.3m, r.Items[0].DowntimeHours);
    }

    [Fact]
    public void Adjacent_windows_are_additive_and_a_spanning_event_counts_once()
    {
        long Minutes(TimeWindow w) => MetricCalculator.DowntimeByLine(ActiveLines, Reasons, Downtime, w, true, 10)
            .Items.Single(i => i.LineCode == "L01").DowntimeMinutes;
        Assert.Equal(30, Minutes(Day(1)));
        Assert.Equal(Minutes(Day(1)) + Minutes(Day(2)), Minutes(new TimeWindow(Utc(2026, 1, 1), Utc(2026, 1, 3))));
        var both = MetricCalculator.DowntimeByLine(ActiveLines, Reasons, Downtime, new TimeWindow(Utc(2026, 1, 1), Utc(2026, 1, 3)), true, 10);
        Assert.Equal(2, both.Items.Single(i => i.LineCode == "L01").EventCount);
    }

    [Fact]
    public void Planned_downtime_can_be_excluded()
    {
        var r = MetricCalculator.DowntimeByLine(ActiveLines, Reasons, Downtime, Day(2), includePlanned: false, topN: 10);
        Assert.Equal(50, r.TotalDowntimeMinutes);
        Assert.Equal([90.0m, 10.0m], r.Items.Select(i => i.SharePct!.Value));
    }

    [Fact]
    public void Empty_window_lists_active_lines_with_zero_and_null_share()
    {
        var r = MetricCalculator.DowntimeByLine(ActiveLines, Reasons, Downtime, Day(20), true, 10);
        Assert.Equal(0, r.TotalDowntimeMinutes);
        Assert.Equal(["L01", "L02"], r.Items.Select(i => i.LineCode));
        Assert.All(r.Items, i => Assert.Null(i.SharePct));
    }

    [Fact]
    public void Top_n_truncates_after_computing_shares()
    {
        var r = MetricCalculator.DowntimeByLine(ActiveLines, Reasons, Downtime, Day(2), true, topN: 1);
        Assert.Single(r.Items);
        Assert.Equal(1, r.OmittedCount);
        Assert.Equal(93.8m, r.Items[0].SharePct);
    }

    [Fact]
    public void Downtime_reasons_group_by_reason_and_omit_empty_reasons()
    {
        var r = MetricCalculator.DowntimeReasons(ActiveLines, Reasons, Downtime, Day(2), true, 10);
        Assert.Equal([("MECH_FAILURE", 50L, 2, 62.5m, false), ("CHANGEOVER", 30L, 1, 37.5m, true)],
            r.Items.Select(i => (i.ReasonCode, i.DowntimeMinutes, i.EventCount, i.SharePct!.Value, i.IsPlanned)));
        var unplanned = MetricCalculator.DowntimeReasons(ActiveLines, Reasons, Downtime, Day(2), false, 10);
        Assert.Equal(["MECH_FAILURE"], unplanned.Items.Select(i => i.ReasonCode));
    }

    [Fact]
    public void Production_summary_totals_and_per_line()
    {
        var r = MetricCalculator.ProductionSummary(ActiveLines, Production, Downtime, Day(2));
        Assert.Equal(new ProductionMetrics(250, 170, 3, 167, 68.0m, 1.8m, 80, 1.3m, 3), r.Totals);
        var l02 = r.ByLine.Single(l => l.LineCode == "L02");
        Assert.Equal(0.0m, l02.AttainmentPct);
        Assert.Null(l02.DefectRatePct);
    }

    [Fact]
    public void Daily_trend_has_one_point_per_day()
    {
        var r = MetricCalculator.DailyTrend(ActiveLines, Production, Downtime,
            [(new DateOnly(2026, 1, 1), Day(1)), (new DateOnly(2026, 1, 2), Day(2))]);
        // 01-01: L01 30 (23:30-24:00) + L02 120 (22:00-24:00) = 150 ; 01-02: 80 (see the by-line test)
        Assert.Equal([150L, 80L], r.Items.Select(p => p.DowntimeMinutes));
        Assert.Equal([0L, 170L], r.Items.Select(p => p.ProducedQuantity));
        Assert.Null(r.Items[0].AttainmentPct);
    }
}
