using System.Globalization;
using System.Text;
using Microsoft.EntityFrameworkCore;
using OpsPilot.Api.Domain;

namespace OpsPilot.Api.Data;

/// <summary>Loads the committed synthetic dataset (sample-data/csv) into an empty database.</summary>
public sealed class CsvSeeder(OpsPilotDbContext db, string csvDirectory)
{
    public async Task SeedAsync(CancellationToken ct)
    {
        db.ChangeTracker.AutoDetectChangesEnabled = false;
        await using var tx = await db.Database.BeginTransactionAsync(ct);

        var lines = Read("production_lines.csv").Select(r => new ProductionLine
        {
            Code = r["Code"], Name = r["Name"], Department = r["Department"],
            NominalRatePerHour = Int(r["NominalRatePerHour"]), IsActive = Bool(r["IsActive"]),
        }).ToList();
        db.ProductionLines.AddRange(lines);
        db.DowntimeReasons.AddRange(Read("downtime_reasons.csv").Select(r => new DowntimeReason
        {
            Code = r["Code"], Name = r["Name"], Category = r["Category"], IsPlanned = Bool(r["IsPlanned"]),
        }));
        await db.SaveChangesAsync(ct);
        var lineId = lines.ToDictionary(l => l.Code, l => l.Id);

        var equipment = Read("equipment.csv").Select(r => new Equipment
        {
            LineId = lineId[r["LineCode"]], EquipmentCode = r["EquipmentCode"], Name = r["Name"],
            EquipmentType = r["EquipmentType"],
        }).ToList();
        db.Equipment.AddRange(equipment);
        await db.SaveChangesAsync(ct);
        var equipmentId = equipment.ToDictionary(e => e.EquipmentCode, e => e.Id);

        db.ProductionRecords.AddRange(Read("production_records.csv").Select(r => new ProductionRecord
        {
            LineId = lineId[r["LineCode"]], PeriodStartUtc = Utc(r["PeriodStartUtc"]),
            PlannedQuantity = Int(r["PlannedQuantity"]), ProducedQuantity = Int(r["ProducedQuantity"]),
            DefectiveQuantity = Int(r["DefectiveQuantity"]),
        }));
        db.DowntimeEvents.AddRange(Read("downtime_events.csv").Select(r => new DowntimeEvent
        {
            Id = Int(r["Id"]), LineId = lineId[r["LineCode"]],
            EquipmentId = r["EquipmentCode"].Length == 0 ? null : equipmentId[r["EquipmentCode"]],
            StartTimeUtc = Utc(r["StartTimeUtc"]), EndTimeUtc = Utc(r["EndTimeUtc"]),
            DurationMinutes = Int(r["DurationMinutes"]), ReasonCode = r["ReasonCode"], Description = r["Description"],
        }));
        db.QualityIncidents.AddRange(Read("quality_incidents.csv").Select(r => new QualityIncident
        {
            Id = Int(r["Id"]), LineId = lineId[r["LineCode"]], OccurredAtUtc = Utc(r["OccurredAtUtc"]),
            Category = r["Category"], Severity = r["Severity"], Status = r["Status"], Description = r["Description"],
        }));
        await db.SaveChangesAsync(ct);

        db.MaintenanceEvents.AddRange(Read("maintenance_events.csv").Select(r => new MaintenanceEvent
        {
            Id = Int(r["Id"]), EquipmentId = equipmentId[r["EquipmentCode"]],
            DowntimeEventId = r["DowntimeEventId"].Length == 0 ? null : Int(r["DowntimeEventId"]),
            OccurredAtUtc = Utc(r["OccurredAtUtc"]), ErrorCode = r["ErrorCode"].Length == 0 ? null : r["ErrorCode"],
            Description = r["Description"], Resolution = r["Resolution"], DurationMinutes = Int(r["DurationMinutes"]),
        }));
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
        db.ChangeTracker.Clear();
    }

    private IEnumerable<Dictionary<string, string>> Read(string fileName)
    {
        using var reader = new StreamReader(Path.Combine(csvDirectory, fileName), Encoding.UTF8);
        var rows = ParseCsv(reader.ReadToEnd());
        var header = rows[0];
        return rows.Skip(1)
            .Select(row => header.Select((h, i) => (h, v: row[i])).ToDictionary(x => x.h, x => x.v))
            .ToList();
    }

    /// <summary>Minimal RFC 4180 parser (quoted fields, escaped quotes, LF or CRLF).</summary>
    internal static List<string[]> ParseCsv(string text)
    {
        var rows = new List<string[]>();
        var fields = new List<string>();
        var field = new StringBuilder();
        var inQuotes = false;
        for (var i = 0; i < text.Length; i++)
        {
            var c = text[i];
            if (inQuotes)
            {
                if (c == '"' && i + 1 < text.Length && text[i + 1] == '"') { field.Append('"'); i++; }
                else if (c == '"') inQuotes = false;
                else field.Append(c);
            }
            else if (c == '"') inQuotes = true;
            else if (c == ',') { fields.Add(field.ToString()); field.Clear(); }
            else if (c == '\n' || c == '\r')
            {
                if (c == '\r' && i + 1 < text.Length && text[i + 1] == '\n') i++;
                fields.Add(field.ToString()); field.Clear();
                rows.Add([.. fields]); fields.Clear();
            }
            else field.Append(c);
        }
        if (field.Length > 0 || fields.Count > 0) { fields.Add(field.ToString()); rows.Add([.. fields]); }
        return rows;
    }

    private static int Int(string v) => int.Parse(v, CultureInfo.InvariantCulture);
    private static bool Bool(string v) => v == "true";

    private static DateTime Utc(string v) => DateTime.ParseExact(v, "yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture,
        DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal);
}
