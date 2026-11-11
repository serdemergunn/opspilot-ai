using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.Options;
using OpsPilot.Api.Analytics;
using OpsPilot.Api.Tools;

namespace OpsPilot.Api.Endpoints;

/// <summary>
/// Internal endpoints called by the AI service. Protected by a shared service key, snake_case JSON,
/// strict schema (unknown properties are rejected).
/// </summary>
public static class ToolEndpoints
{
    public const string ServiceKeyHeader = "X-OpsPilot-Service-Key";

    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        DefaultIgnoreCondition = JsonIgnoreCondition.Never,
    };

    public static void MapToolEndpoints(this IEndpointRouteBuilder app)
    {
        var group = app.MapGroup("/internal/tools").AddEndpointFilter(RequireServiceKey);

        group.MapGet("/", () => Results.Json(new
        {
            tools = ToolRegistry.Tools.Values.Select(t => new { name = t.Name, description = t.Description, input_schema = t.InputSchema }),
        }, Json));

        group.MapPost("/{toolName}", ExecuteAsync);
    }

    private static async Task<IResult> ExecuteAsync(
        string toolName, HttpRequest request, AnalyticsService analytics, PlantClock clock,
        IOptions<OpsPilotOptions> options, ILoggerFactory loggerFactory, CancellationToken requestAborted)
    {
        var logger = loggerFactory.CreateLogger("OpsPilot.Tools");
        if (!ToolRegistry.Tools.TryGetValue(toolName, out var tool))
        {
            logger.LogWarning("Rejected unknown tool {Tool}", Sanitize(toolName));
            return Results.Json(new { tool = Sanitize(toolName), status = "unknown_tool" }, Json, statusCode: StatusCodes.Status404NotFound);
        }

        var sw = Stopwatch.StartNew();
        AnalyticsQuery query;
        try
        {
            var args = await JsonSerializer.DeserializeAsync<ToolArguments>(request.Body, Json, requestAborted)
                ?? throw new JsonException("Body must be a JSON object.");
            query = ToolArgumentValidator.Validate(args, tool.SupportsDowntimeOptions, clock.Today);
        }
        catch (JsonException ex)
        {
            return Invalid(tool.Name, new Dictionary<string, string[]> { ["$"] = [DescribeJsonError(ex)] });
        }
        catch (ToolValidationException ex)
        {
            return Invalid(tool.Name, ex.Errors);
        }

        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(requestAborted);
        timeout.CancelAfter(TimeSpan.FromSeconds(options.Value.Tools.TimeoutSeconds));
        try
        {
            var result = await tool.Execute(analytics, query, timeout.Token);
            logger.LogInformation(
                "Tool {Tool} succeeded in {DurationMs} ms for {StartDate}..{EndDate} lines={LineCodes} rows={RowCount}",
                tool.Name, sw.ElapsedMilliseconds, query.StartDate.ToString("yyyy-MM-dd"), query.EndDate.ToString("yyyy-MM-dd"),
                query.LineCodes is null ? "all" : string.Join(",", query.LineCodes), result.Meta.RowCount);
            return Results.Json(new { tool = tool.Name, status = "ok", data = result.Data, meta = result.Meta }, Json);
        }
        catch (ToolValidationException ex)
        {
            return Invalid(tool.Name, ex.Errors);
        }
        catch (OperationCanceledException) when (timeout.IsCancellationRequested && !requestAborted.IsCancellationRequested)
        {
            logger.LogWarning("Tool {Tool} timed out after {DurationMs} ms", tool.Name, sw.ElapsedMilliseconds);
            return Results.Json(new { tool = tool.Name, status = "timeout" }, Json, statusCode: StatusCodes.Status504GatewayTimeout);
        }

        IResult Invalid(string name, IReadOnlyDictionary<string, string[]> errors)
        {
            logger.LogInformation("Tool {Tool} rejected invalid arguments: {Fields}", name, string.Join(",", errors.Keys));
            return Results.Json(new { tool = name, status = "invalid_arguments", errors }, Json,
                statusCode: StatusCodes.Status422UnprocessableEntity);
        }
    }

    private static async ValueTask<object?> RequireServiceKey(EndpointFilterInvocationContext ctx, EndpointFilterDelegate next)
    {
        var expected = ctx.HttpContext.RequestServices.GetRequiredService<IOptions<OpsPilotOptions>>().Value.Tools.ServiceKey;
        var provided = ctx.HttpContext.Request.Headers[ServiceKeyHeader].ToString();
        // Fail closed when no key is configured; compare in constant time.
        if (string.IsNullOrEmpty(expected) ||
            !CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(provided), Encoding.UTF8.GetBytes(expected)))
        {
            return Results.Json(new { status = "unauthorized" }, Json, statusCode: StatusCodes.Status401Unauthorized);
        }
        return await next(ctx);
    }

    private static string DescribeJsonError(JsonException ex) =>
        ex.Path is { Length: > 0 } path ? $"Invalid value or unknown property at '{path}'." : "Body must be a JSON object matching the tool schema.";

    private static string Sanitize(string value) =>
        new(value.Take(64).Where(c => char.IsLetterOrDigit(c) || c == '_').ToArray());
}
