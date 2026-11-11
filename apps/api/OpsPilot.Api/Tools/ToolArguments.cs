using System.Globalization;
using System.Text.RegularExpressions;

namespace OpsPilot.Api.Tools;

/// <summary>
/// Raw tool arguments as received over the wire (snake_case JSON). Kept loosely typed so that invalid input
/// produces specific, field-level messages the agent can act on, instead of a generic deserialization error.
/// </summary>
public sealed class ToolArguments
{
    public string? StartDate { get; init; }
    public string? EndDate { get; init; }
    public List<string>? LineCodes { get; init; }
    public bool? IncludePlanned { get; init; }
    public int? TopN { get; init; }
}

/// <summary>Validated, bounded query. Only constructed by <see cref="ToolArgumentValidator"/>.</summary>
public sealed record AnalyticsQuery(
    DateOnly StartDate, DateOnly EndDate, IReadOnlyList<string>? LineCodes, bool IncludePlanned, int TopN);

public sealed class ToolValidationException(IReadOnlyDictionary<string, string[]> errors)
    : Exception("Tool arguments are invalid.")
{
    public IReadOnlyDictionary<string, string[]> Errors { get; } = errors;
}

public static partial class ToolArgumentValidator
{
    public const int MaxRangeDays = 92;
    public const int MaxLookbackDays = 366;
    public const int MaxLineCodes = 10;
    public const int MaxTopN = 20;
    public const int DefaultTopN = 10;

    [GeneratedRegex(@"^L\d{2}$")]
    private static partial Regex LineCodePattern();

    /// <param name="supportsDowntimeOptions">Whether include_planned and top_n are part of this tool's schema.</param>
    /// <param name="today">Plant-local "today" from the (possibly pinned) clock.</param>
    public static AnalyticsQuery Validate(ToolArguments a, bool supportsDowntimeOptions, DateOnly today)
    {
        var errors = new Dictionary<string, string[]>();
        void Error(string field, string message) => errors[field] = [.. errors.GetValueOrDefault(field, []), message];

        var start = ParseDate(a.StartDate, "start_date", Error);
        var end = ParseDate(a.EndDate, "end_date", Error);
        if (start is { } s && end is { } e)
        {
            if (e < s) Error("end_date", "end_date must be on or after start_date.");
            else if (e.DayNumber - s.DayNumber + 1 > MaxRangeDays) Error("end_date", $"The range may cover at most {MaxRangeDays} days.");
            if (e > today) Error("end_date", $"end_date must not be after today ({today:yyyy-MM-dd}).");
            if (s < today.AddDays(-MaxLookbackDays)) Error("start_date", $"start_date must be within {MaxLookbackDays} days of today.");
        }

        if (a.LineCodes is { } codes)
        {
            if (codes.Count is 0 or > MaxLineCodes) Error("line_codes", $"Provide between 1 and {MaxLineCodes} line codes, or omit the field.");
            if (codes.Any(c => c is null || !LineCodePattern().IsMatch(c))) Error("line_codes", "Line codes must look like 'L01'.");
            if (codes.Distinct(StringComparer.Ordinal).Count() != codes.Count) Error("line_codes", "Line codes must be unique.");
        }

        if (!supportsDowntimeOptions)
        {
            if (a.IncludePlanned is not null) Error("include_planned", "Not a parameter of this tool.");
            if (a.TopN is not null) Error("top_n", "Not a parameter of this tool.");
        }
        else if (a.TopN is { } n && (n < 1 || n > MaxTopN))
        {
            Error("top_n", $"top_n must be between 1 and {MaxTopN}.");
        }

        if (errors.Count > 0) throw new ToolValidationException(errors);
        return new AnalyticsQuery(start!.Value, end!.Value, a.LineCodes, a.IncludePlanned ?? true, a.TopN ?? DefaultTopN);
    }

    private static DateOnly? ParseDate(string? value, string field, Action<string, string> error)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            error(field, $"{field} is required (YYYY-MM-DD).");
            return null;
        }
        if (!DateOnly.TryParseExact(value, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var d))
        {
            error(field, $"{field} must be a date in YYYY-MM-DD format.");
            return null;
        }
        return d;
    }
}
