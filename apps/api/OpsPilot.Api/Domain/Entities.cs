namespace OpsPilot.Api.Domain;

// Persistence entities. All DateTime values are UTC (enforced by a value converter in OpsPilotDbContext).

public sealed class ProductionLine
{
    public int Id { get; set; }
    public required string Code { get; set; }
    public required string Name { get; set; }
    public required string Department { get; set; }
    public int NominalRatePerHour { get; set; }
    public bool IsActive { get; set; }
}

public sealed class Equipment
{
    public int Id { get; set; }
    public int LineId { get; set; }
    public ProductionLine? Line { get; set; }
    public required string EquipmentCode { get; set; }
    public required string Name { get; set; }
    public required string EquipmentType { get; set; }
}

public sealed class DowntimeReason
{
    public required string Code { get; set; }
    public required string Name { get; set; }
    public required string Category { get; set; }
    public bool IsPlanned { get; set; }
}

/// <summary>One-hour production bucket starting at <see cref="PeriodStartUtc"/>.</summary>
public sealed class ProductionRecord
{
    public long Id { get; set; }
    public int LineId { get; set; }
    public ProductionLine? Line { get; set; }
    public DateTime PeriodStartUtc { get; set; }
    public int PlannedQuantity { get; set; }
    public int ProducedQuantity { get; set; }
    public int DefectiveQuantity { get; set; }
}

public sealed class DowntimeEvent
{
    public int Id { get; set; }
    public int LineId { get; set; }
    public ProductionLine? Line { get; set; }
    public int? EquipmentId { get; set; }
    public Equipment? Equipment { get; set; }
    public DateTime StartTimeUtc { get; set; }
    public DateTime EndTimeUtc { get; set; }
    public int DurationMinutes { get; set; }
    public required string ReasonCode { get; set; }
    public DowntimeReason? Reason { get; set; }
    public required string Description { get; set; }
}

public sealed class QualityIncident
{
    public int Id { get; set; }
    public int LineId { get; set; }
    public ProductionLine? Line { get; set; }
    public DateTime OccurredAtUtc { get; set; }
    public required string Category { get; set; }
    public required string Severity { get; set; }
    public required string Status { get; set; }
    public required string Description { get; set; }
}

public sealed class MaintenanceEvent
{
    public int Id { get; set; }
    public int EquipmentId { get; set; }
    public Equipment? Equipment { get; set; }
    public int? DowntimeEventId { get; set; }
    public DowntimeEvent? DowntimeEvent { get; set; }
    public DateTime OccurredAtUtc { get; set; }
    public string? ErrorCode { get; set; }
    public required string Description { get; set; }
    public required string Resolution { get; set; }
    public int DurationMinutes { get; set; }
}
