using Microsoft.Extensions.Options;

namespace OpsPilot.Api.Analytics;

public sealed class OpsPilotOptions
{
    public ClockOptions Clock { get; set; } = new();
    public PlantOptions Plant { get; set; } = new();
    public ToolOptions Tools { get; set; } = new();

    public sealed class ClockOptions
    {
        /// <summary>Pinned "now" for demo, tests and evaluation. Null means wall clock.</summary>
        public DateTimeOffset? ReferenceTimeUtc { get; set; }
    }

    public sealed class PlantOptions
    {
        /// <summary>IANA time zone id of the plant, e.g. "UTC" or "Europe/Berlin".</summary>
        public string TimeZone { get; set; } = "UTC";
    }

    public sealed class ToolOptions
    {
        /// <summary>Shared secret the AI service sends in X-OpsPilot-Service-Key. Empty disables tool endpoints.</summary>
        public string ServiceKey { get; set; } = "";
        public int TimeoutSeconds { get; set; } = 10;
    }
}

/// <summary>Half-open UTC interval [StartUtc, EndUtc).</summary>
public readonly record struct TimeWindow(DateTime StartUtc, DateTime EndUtc);

/// <summary>Resolves plant-local calendar dates to UTC windows against a (possibly pinned) clock.</summary>
public sealed class PlantClock
{
    private readonly DateTimeOffset? _reference;
    private readonly TimeProvider _time;

    public PlantClock(IOptions<OpsPilotOptions> options, TimeProvider time)
    {
        _reference = options.Value.Clock.ReferenceTimeUtc;
        _time = time;
        Zone = TimeZoneInfo.FindSystemTimeZoneById(options.Value.Plant.TimeZone);
    }

    public TimeZoneInfo Zone { get; }

    public DateTimeOffset NowUtc => _reference ?? _time.GetUtcNow();

    public bool IsPinned => _reference is not null;

    public DateOnly Today => DateOnly.FromDateTime(TimeZoneInfo.ConvertTimeFromUtc(NowUtc.UtcDateTime, Zone));

    /// <summary>Inclusive local dates to [start 00:00 local, (end + 1 day) 00:00 local) in UTC.</summary>
    public TimeWindow ToUtcWindow(DateOnly start, DateOnly endInclusive) =>
        new(LocalMidnightUtc(start), LocalMidnightUtc(endInclusive.AddDays(1)));

    public DateOnly LocalDateOf(DateTime utc) => DateOnly.FromDateTime(TimeZoneInfo.ConvertTimeFromUtc(utc, Zone));

    private DateTime LocalMidnightUtc(DateOnly date)
    {
        var local = date.ToDateTime(TimeOnly.MinValue, DateTimeKind.Unspecified);
        // Some zones skip midnight on DST change; the day then starts at the first valid local time.
        while (Zone.IsInvalidTime(local)) local = local.AddMinutes(15);
        return TimeZoneInfo.ConvertTimeToUtc(local, Zone);
    }
}
