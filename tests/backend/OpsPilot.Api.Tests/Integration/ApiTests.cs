using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Nodes;
using Microsoft.Data.SqlClient;

namespace OpsPilot.Api.Tests.Integration;

/// <summary>
/// Every golden case produced by the independent Python oracle (sample-data/reference_metrics.py) must be
/// reproduced exactly by the API, end to end: HTTP -> validation -> SQL Server -> calculator -> JSON.
/// </summary>
[Collection(ApiCollection.Name)]
public class GoldenParityTests(ApiFixture fx)
{
    private static readonly JsonObject Golden =
        JsonNode.Parse(File.ReadAllText(Path.Combine(ApiFixture.RepoRoot, "sample-data", "golden", "expected_metrics.json")))!.AsObject();

    public static IEnumerable<object[]> CaseIds() => Golden["cases"]!.AsArray().Select(c => new object[] { (string)c!["id"]! });

    [Theory]
    [MemberData(nameof(CaseIds))]
    public async Task Tool_output_matches_oracle(string caseId)
    {
        var c = Golden["cases"]!.AsArray().Single(x => (string)x!["id"]! == caseId)!;
        using var client = fx.CreateClient(withServiceKey: true);

        var response = await client.PostAsJsonAsync($"/internal/tools/{(string)c["tool"]!}", c["arguments"]);
        var body = await response.Content.ReadAsStringAsync();

        Assert.True(response.StatusCode == HttpStatusCode.OK, body);
        var json = JsonNode.Parse(body)!;
        Assert.Equal("ok", (string)json["status"]!);
        JsonAssert.Equivalent(c["expected"], json["data"], "$");
    }
}

[Collection(ApiCollection.Name)]
public class ToolEndpointSecurityTests(ApiFixture fx)
{
    private static readonly object ValidArgs = new { start_date = "2026-11-04", end_date = "2026-11-10" };

    [Fact]
    public async Task Missing_service_key_is_rejected()
    {
        using var client = fx.CreateClient();
        var r = await client.PostAsJsonAsync("/internal/tools/get_downtime_by_line", ValidArgs);
        Assert.Equal(HttpStatusCode.Unauthorized, r.StatusCode);
    }

    [Fact]
    public async Task Wrong_service_key_is_rejected()
    {
        using var client = fx.CreateClient();
        client.DefaultRequestHeaders.Add("X-OpsPilot-Service-Key", "not-the-key");
        Assert.Equal(HttpStatusCode.Unauthorized, (await client.GetAsync("/internal/tools")).StatusCode);
    }

    [Fact]
    public async Task Unknown_tool_is_not_found()
    {
        using var client = fx.CreateClient(withServiceKey: true);
        var r = await client.PostAsJsonAsync("/internal/tools/execute_sql", new { query = "SELECT 1" });
        Assert.Equal(HttpStatusCode.NotFound, r.StatusCode);
        Assert.Equal("unknown_tool", (string)JsonNode.Parse(await r.Content.ReadAsStringAsync())!["status"]!);
    }

    public static TheoryData<string, string, string> InvalidRequests => new()
    {
        { "get_downtime_by_line", """{"start_date":"2026-11-04","end_date":"2026-11-10","sql":"DROP TABLE x"}""", "$" },
        { "get_downtime_by_line", """{"start_date":"2026-01-01","end_date":"2026-11-10"}""", "end_date" },
        { "get_downtime_by_line", """{"start_date":"2026-11-04","end_date":"2026-11-10","line_codes":["L99"]}""", "line_codes" },
        { "get_downtime_by_line", """{"start_date":"2026-11-04","end_date":"2026-11-10","top_n":500}""", "top_n" },
        { "get_production_summary", """{"start_date":"2026-11-04","end_date":"2026-11-10","top_n":3}""", "top_n" },
        { "get_downtime_reasons", """{"start_date":"2026-11-04' OR 1=1--","end_date":"2026-11-10"}""", "start_date" },
        { "get_downtime_reasons", """[1,2,3]""", "$" },
    };

    [Theory]
    [MemberData(nameof(InvalidRequests))]
    public async Task Invalid_arguments_return_422_with_field_errors(string tool, string body, string field)
    {
        using var client = fx.CreateClient(withServiceKey: true);
        var r = await client.PostAsync($"/internal/tools/{tool}", new StringContent(body, System.Text.Encoding.UTF8, "application/json"));
        var json = JsonNode.Parse(await r.Content.ReadAsStringAsync())!;
        Assert.Equal(HttpStatusCode.UnprocessableEntity, r.StatusCode);
        Assert.Equal("invalid_arguments", (string)json["status"]!);
        Assert.NotNull(json["errors"]![field]);
    }

    [Fact]
    public async Task Tool_listing_publishes_strict_schemas()
    {
        using var client = fx.CreateClient(withServiceKey: true);
        var json = JsonNode.Parse(await client.GetStringAsync("/internal/tools"))!;
        var tools = json["tools"]!.AsArray();
        Assert.Equal(
            ["get_daily_production_trend", "get_downtime_by_line", "get_downtime_reasons", "get_production_summary"],
            tools.Select(t => (string)t!["name"]!).Order());
        Assert.All(tools, t => Assert.False((bool)t!["input_schema"]!["additionalProperties"]!));
    }
}

[Collection(ApiCollection.Name)]
public class DatabaseAndPublicEndpointTests(ApiFixture fx)
{
    [Fact]
    public async Task Request_login_is_read_only()
    {
        await using var conn = new SqlConnection(fx.ReaderConnectionString);
        await conn.OpenAsync();
        await using var read = new SqlCommand("SELECT COUNT(*) FROM DowntimeReasons", conn);
        Assert.Equal(7, (int)(await read.ExecuteScalarAsync())!);
        await using var write = new SqlCommand("DELETE FROM DowntimeReasons", conn);
        var ex = await Assert.ThrowsAsync<SqlException>(() => write.ExecuteNonQueryAsync());
        Assert.Contains("permission", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task Seeded_row_counts_match_the_dataset()
    {
        await using var conn = new SqlConnection(fx.ReaderConnectionString);
        await conn.OpenAsync();
        async Task<int> Count(string table)
        {
            await using var cmd = new SqlCommand($"SELECT COUNT(*) FROM [{table}]", conn);
            return (int)(await cmd.ExecuteScalarAsync())!;
        }
        Assert.Equal(12960, await Count("ProductionRecords"));
        Assert.Equal(CsvRows("downtime_events.csv"), await Count("DowntimeEvents"));
        Assert.Equal(CsvRows("quality_incidents.csv"), await Count("QualityIncidents"));
        Assert.Equal(CsvRows("maintenance_events.csv"), await Count("MaintenanceEvents"));
    }

    [Fact]
    public async Task Public_endpoint_returns_camel_case_and_the_seeded_story()
    {
        using var client = fx.CreateClient();
        var json = JsonNode.Parse(await client.GetStringAsync("/api/analytics/downtime-by-line?startDate=2026-11-04&endDate=2026-11-10"))!;
        Assert.Equal("L04", (string)json["data"]!["items"]![0]!["lineCode"]!);
        Assert.NotNull(json["meta"]!["windowStartUtc"]);
    }

    [Fact]
    public async Task Public_endpoint_returns_problem_details_on_invalid_input()
    {
        using var client = fx.CreateClient();
        var r = await client.GetAsync("/api/analytics/downtime-reasons?startDate=2026-11-10&endDate=2026-11-01");
        Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
        Assert.Equal("application/problem+json", r.Content.Headers.ContentType?.MediaType);
        Assert.NotNull(JsonNode.Parse(await r.Content.ReadAsStringAsync())!["errors"]!["endDate"]);
    }

    [Fact]
    public async Task Meta_reports_pinned_clock_and_dataset_range()
    {
        using var client = fx.CreateClient();
        var json = JsonNode.Parse(await client.GetStringAsync("/api/meta"))!;
        Assert.Equal("2026-11-11", (string)json["today"]!);
        Assert.True((bool)json["clockPinned"]!);
        Assert.Equal("2026-08-13", (string)json["dataset"]!["firstDate"]!);
        Assert.Equal("2026-11-10", (string)json["dataset"]!["lastDate"]!);
    }

    private static int CsvRows(string file) =>
        File.ReadAllLines(Path.Combine(ApiFixture.RepoRoot, "sample-data", "csv", file)).Length - 1;
}

internal static class JsonAssert
{
    /// <summary>Structural equality; numbers compare by decimal value (68 == 68.0).</summary>
    public static void Equivalent(JsonNode? expected, JsonNode? actual, string path)
    {
        switch (expected)
        {
            case null:
                Assert.True(actual is null, $"{path}: expected null, got {actual?.ToJsonString()}");
                break;
            case JsonObject eo:
                var ao = Assert.IsType<JsonObject>(actual);
                Assert.True(eo.Select(p => p.Key).Order().SequenceEqual(ao.Select(p => p.Key).Order()),
                    $"{path}: keys differ. expected [{string.Join(",", eo.Select(p => p.Key))}] actual [{string.Join(",", ao.Select(p => p.Key))}]");
                foreach (var (k, v) in eo) Equivalent(v, ao[k], $"{path}.{k}");
                break;
            case JsonArray ea:
                var aa = Assert.IsType<JsonArray>(actual);
                Assert.True(ea.Count == aa.Count, $"{path}: expected {ea.Count} items, got {aa.Count}");
                for (var i = 0; i < ea.Count; i++) Equivalent(ea[i], aa[i], $"{path}[{i}]");
                break;
            case JsonValue ev when ev.TryGetValue<decimal>(out var en):
                Assert.True(actual is JsonValue av && av.TryGetValue<decimal>(out var an) && an == en,
                    $"{path}: expected {en}, got {actual?.ToJsonString()}");
                break;
            default:
                Assert.True(JsonNode.DeepEquals(expected, actual), $"{path}: expected {expected.ToJsonString()}, got {actual?.ToJsonString()}");
                break;
        }
    }
}
