using System.Net;
using System.Net.Http.Json;
using Microsoft.Extensions.Options;
using OpsPilot.Api.Analytics;

namespace OpsPilot.Api.Endpoints;

public sealed record ChatMessageDto(string? Role, string? Content);

public sealed record ChatRequestDto(List<ChatMessageDto>? Messages, string? Mode);

/// <summary>
/// The browser's only way to reach the agent (ADR 0002). Validates the request, forwards it to the internal
/// AI service with the service key, and maps failures to problem details. The response body is passed through
/// unchanged (snake_case, as defined by the AI service contract).
/// </summary>
public static class ChatEndpoints
{
    public const string HttpClientName = "ai-service";
    public const string RateLimitPolicy = "chat";
    public const int MaxMessages = 20;
    public const int MaxContentLength = 4_000;
    public const int MaxConversationLength = 16_000;
    public const long MaxBodyBytes = 64 * 1024;

    public static void MapChatEndpoints(this IEndpointRouteBuilder app)
    {
        app.MapPost("/api/chat", ChatAsync)
            .RequireRateLimiting(RateLimitPolicy)
            .WithMetadata(new Microsoft.AspNetCore.Mvc.RequestSizeLimitAttribute(MaxBodyBytes));
    }

    internal static Dictionary<string, string[]> Validate(ChatRequestDto body)
    {
        var errors = new Dictionary<string, string[]>();
        var messages = body.Messages ?? [];
        if (messages.Count is 0 or > MaxMessages) errors["messages"] = [$"Provide between 1 and {MaxMessages} messages."];
        else if (messages.Any(m => m.Role is not ("user" or "assistant"))) errors["messages"] = ["Each message role must be 'user' or 'assistant'."];
        else if (messages.Any(m => string.IsNullOrWhiteSpace(m.Content) || m.Content.Length > MaxContentLength))
            errors["messages"] = [$"Each message needs content of at most {MaxContentLength} characters."];
        else if (messages[^1].Role != "user") errors["messages"] = ["The last message must come from the user."];
        else if (messages.Sum(m => m.Content!.Length) > MaxConversationLength)
            errors["messages"] = [$"The conversation may contain at most {MaxConversationLength} characters."];
        if (body.Mode is not (null or "demo" or "live")) errors["mode"] = ["Mode must be 'demo' or 'live'."];
        return errors;
    }

    private static async Task<IResult> ChatAsync(
        ChatRequestDto body, IHttpClientFactory httpClientFactory, IOptions<OpsPilotOptions> options,
        ILoggerFactory loggerFactory, CancellationToken ct)
    {
        var errors = Validate(body);
        if (errors.Count > 0) return Results.ValidationProblem(errors);

        var logger = loggerFactory.CreateLogger("OpsPilot.Chat");
        var client = httpClientFactory.CreateClient(HttpClientName);
        using var request = new HttpRequestMessage(HttpMethod.Post, "/v1/chat")
        {
            Content = JsonContent.Create(new
            {
                messages = body.Messages!.Select(m => new { role = m.Role, content = m.Content }),
                mode = body.Mode,
            }),
        };
        request.Headers.Add(ToolEndpoints.ServiceKeyHeader, options.Value.Tools.ServiceKey);

        HttpResponseMessage response;
        try
        {
            response = await client.SendAsync(request, ct);
        }
        catch (HttpRequestException ex)
        {
            logger.LogWarning("AI service unreachable: {Error}", ex.Message);
            return Problem(StatusCodes.Status503ServiceUnavailable, "The AI service is unavailable.");
        }
        catch (TaskCanceledException) when (!ct.IsCancellationRequested)
        {
            return Problem(StatusCodes.Status504GatewayTimeout, "The AI service did not answer in time.");
        }

        using (response)
        {
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync(ct);
                return Results.Content(json, "application/json");
            }
            logger.LogWarning("AI service returned {Status}", (int)response.StatusCode);
            return response.StatusCode switch
            {
                HttpStatusCode.GatewayTimeout => Problem(StatusCodes.Status504GatewayTimeout, "The AI service did not answer in time."),
                HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden =>
                    Problem(StatusCodes.Status502BadGateway, "The AI service rejected the API's credentials. Check OPSPILOT_SERVICE_KEY."),
                _ => Problem(StatusCodes.Status502BadGateway, "The AI service failed to answer."),
            };
        }
    }

    private static IResult Problem(int status, string title) => Results.Problem(title: title, statusCode: status);
}
