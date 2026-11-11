using Microsoft.Extensions.Options;
using OpsPilot.Api.Analytics;
using OpsPilot.Api.Data;
using OpsPilot.Api.Tools;

namespace OpsPilot.Api.Tests.Unit;

public class ToolArgumentValidatorTests
{
    private static readonly DateOnly Today = new(2026, 11, 11);

    private static IReadOnlyDictionary<string, string[]> Errors(ToolArguments a, bool downtimeOptions = true) =>
        Assert.Throws<ToolValidationException>(() => ToolArgumentValidator.Validate(a, downtimeOptions, Today)).Errors;

    [Fact]
    public void Valid_arguments_apply_defaults()
    {
        var q = ToolArgumentValidator.Validate(new ToolArguments { StartDate = "2026-11-04", EndDate = "2026-11-10" }, true, Today);
        Assert.Equal(new DateOnly(2026, 11, 4), q.StartDate);
        Assert.True(q.IncludePlanned);
        Assert.Equal(10, q.TopN);
        Assert.Null(q.LineCodes);
    }

    [Theory]
    [InlineData(null, "2026-11-10", "start_date")]
    [InlineData("2026/11/04", "2026-11-10", "start_date")]
    [InlineData("2026-11-01'; DROP TABLE DowntimeEvents;--", "2026-11-10", "start_date")]
    [InlineData("2026-11-10", "2026-11-04", "end_date")]       // reversed
    [InlineData("2026-08-01", "2026-11-10", "end_date")]       // 102 days > 92
    [InlineData("2026-11-10", "2026-11-12", "end_date")]       // in the future
    [InlineData("2025-01-01", "2025-01-31", "start_date")]     // beyond look-back
    public void Invalid_dates_are_rejected(string? start, string end, string field) =>
        Assert.Contains(field, Errors(new ToolArguments { StartDate = start, EndDate = end }).Keys);

    [Fact]
    public void Range_of_exactly_92_days_is_allowed() =>
        ToolArgumentValidator.Validate(new ToolArguments { StartDate = "2026-08-11", EndDate = "2026-11-10" }, true, Today);

    public static TheoryData<string[]> BadLineCodes => new()
    {
        Array.Empty<string>(),
        new[] { "Line 01" },
        new[] { "L01", "L01" },
        new[] { "L01", "L02", "L03", "L04", "L05", "L06", "L07", "L08", "L09", "L10", "L11" },
    };

    [Theory]
    [MemberData(nameof(BadLineCodes))]
    public void Invalid_line_codes_are_rejected(string[] codes) =>
        Assert.Contains("line_codes", Errors(new ToolArguments { StartDate = "2026-11-04", EndDate = "2026-11-10", LineCodes = [.. codes] }).Keys);

    [Theory]
    [InlineData(0)]
    [InlineData(21)]
    public void Top_n_is_bounded(int topN) =>
        Assert.Contains("top_n", Errors(new ToolArguments { StartDate = "2026-11-04", EndDate = "2026-11-10", TopN = topN }).Keys);

    [Fact]
    public void Downtime_options_are_rejected_for_tools_that_do_not_declare_them()
    {
        var errors = Errors(new ToolArguments { StartDate = "2026-11-04", EndDate = "2026-11-10", TopN = 3, IncludePlanned = false },
            downtimeOptions: false);
        Assert.Contains("top_n", errors.Keys);
        Assert.Contains("include_planned", errors.Keys);
    }
}

public class PlantClockTests
{
    private static PlantClock Clock(string zone, string reference) => new(
        Options.Create(new OpsPilotOptions
        {
            Plant = { TimeZone = zone },
            Clock = { ReferenceTimeUtc = DateTimeOffset.Parse(reference, System.Globalization.CultureInfo.InvariantCulture) },
        }),
        TimeProvider.System);

    [Fact]
    public void Utc_plant_maps_dates_to_utc_days()
    {
        var c = Clock("UTC", "2026-11-11T00:00:00Z");
        Assert.Equal(new DateOnly(2026, 11, 11), c.Today);
        var w = c.ToUtcWindow(new DateOnly(2026, 11, 4), new DateOnly(2026, 11, 10));
        Assert.Equal(new DateTime(2026, 11, 4, 0, 0, 0, DateTimeKind.Utc), w.StartUtc);
        Assert.Equal(new DateTime(2026, 11, 11, 0, 0, 0, DateTimeKind.Utc), w.EndUtc);
    }

    [Fact]
    public void Today_follows_the_plant_time_zone() =>
        Assert.Equal(new DateOnly(2026, 11, 11), Clock("Europe/Berlin", "2026-11-10T23:30:00Z").Today);

    [Fact]
    public void Dst_start_day_is_23_hours_long()
    {
        var w = Clock("Europe/Berlin", "2026-11-11T00:00:00Z").ToUtcWindow(new DateOnly(2026, 3, 29), new DateOnly(2026, 3, 29));
        Assert.Equal(new DateTime(2026, 3, 28, 23, 0, 0, DateTimeKind.Utc), w.StartUtc);
        Assert.Equal(new DateTime(2026, 3, 29, 22, 0, 0, DateTimeKind.Utc), w.EndUtc);
    }
}

public class CsvParserTests
{
    [Fact]
    public void Parses_quoted_fields_with_commas_and_escaped_quotes()
    {
        var rows = CsvSeeder.ParseCsv("A,B\n1,\"x, \"\"y\"\"\"\n2,\r\n");
        Assert.Equal(3, rows.Count);
        Assert.Equal(["1", "x, \"y\""], rows[1]);
        Assert.Equal(["2", ""], rows[2]);
    }
}
