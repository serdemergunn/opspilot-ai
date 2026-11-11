using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage.ValueConversion;
using OpsPilot.Api.Domain;

namespace OpsPilot.Api.Data;

public sealed class OpsPilotDbContext(DbContextOptions<OpsPilotDbContext> options) : DbContext(options)
{
    public DbSet<ProductionLine> ProductionLines => Set<ProductionLine>();
    public DbSet<Equipment> Equipment => Set<Equipment>();
    public DbSet<DowntimeReason> DowntimeReasons => Set<DowntimeReason>();
    public DbSet<ProductionRecord> ProductionRecords => Set<ProductionRecord>();
    public DbSet<DowntimeEvent> DowntimeEvents => Set<DowntimeEvent>();
    public DbSet<QualityIncident> QualityIncidents => Set<QualityIncident>();
    public DbSet<MaintenanceEvent> MaintenanceEvents => Set<MaintenanceEvent>();

    protected override void ConfigureConventions(ModelConfigurationBuilder builder)
    {
        // Persist UTC only; read values back as DateTimeKind.Utc.
        builder.Properties<DateTime>().HaveConversion<UtcConverter>().HaveColumnType("datetime2(0)");
    }

    protected override void OnModelCreating(ModelBuilder b)
    {
        b.Entity<ProductionLine>(e =>
        {
            e.Property(x => x.Code).HasMaxLength(8);
            e.Property(x => x.Name).HasMaxLength(64);
            e.Property(x => x.Department).HasMaxLength(64);
            e.HasIndex(x => x.Code).IsUnique();
        });

        b.Entity<Equipment>(e =>
        {
            e.Property(x => x.EquipmentCode).HasMaxLength(32);
            e.Property(x => x.Name).HasMaxLength(64);
            e.Property(x => x.EquipmentType).HasMaxLength(32);
            e.HasIndex(x => x.EquipmentCode).IsUnique();
            e.HasOne(x => x.Line).WithMany().HasForeignKey(x => x.LineId).OnDelete(DeleteBehavior.Restrict);
        });

        b.Entity<DowntimeReason>(e =>
        {
            e.HasKey(x => x.Code);
            e.Property(x => x.Code).HasMaxLength(32);
            e.Property(x => x.Name).HasMaxLength(64);
            e.Property(x => x.Category).HasMaxLength(32);
        });

        b.Entity<ProductionRecord>(e =>
        {
            e.HasIndex(x => new { x.LineId, x.PeriodStartUtc }).IsUnique();
            e.HasIndex(x => x.PeriodStartUtc);
            e.HasOne(x => x.Line).WithMany().HasForeignKey(x => x.LineId).OnDelete(DeleteBehavior.Restrict);
            e.ToTable(t =>
            {
                t.HasCheckConstraint("CK_ProductionRecords_Quantities",
                    "[PlannedQuantity] >= 0 AND [ProducedQuantity] >= 0 AND [DefectiveQuantity] >= 0 AND [DefectiveQuantity] <= [ProducedQuantity]");
            });
        });

        b.Entity<DowntimeEvent>(e =>
        {
            e.Property(x => x.Id).ValueGeneratedNever();
            e.Property(x => x.ReasonCode).HasMaxLength(32);
            e.Property(x => x.Description).HasMaxLength(256);
            e.HasIndex(x => new { x.LineId, x.StartTimeUtc }).IncludeProperties(x => new { x.EndTimeUtc, x.ReasonCode });
            e.HasOne(x => x.Line).WithMany().HasForeignKey(x => x.LineId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.Equipment).WithMany().HasForeignKey(x => x.EquipmentId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.Reason).WithMany().HasForeignKey(x => x.ReasonCode).OnDelete(DeleteBehavior.Restrict);
            e.ToTable(t =>
            {
                t.HasCheckConstraint("CK_DowntimeEvents_Interval", "[EndTimeUtc] > [StartTimeUtc]");
                t.HasCheckConstraint("CK_DowntimeEvents_Duration", "[DurationMinutes] = DATEDIFF(minute, [StartTimeUtc], [EndTimeUtc])");
            });
        });

        b.Entity<QualityIncident>(e =>
        {
            e.Property(x => x.Id).ValueGeneratedNever();
            e.Property(x => x.Category).HasMaxLength(64);
            e.Property(x => x.Severity).HasMaxLength(16);
            e.Property(x => x.Status).HasMaxLength(16);
            e.Property(x => x.Description).HasMaxLength(256);
            e.HasIndex(x => new { x.LineId, x.OccurredAtUtc });
            e.HasOne(x => x.Line).WithMany().HasForeignKey(x => x.LineId).OnDelete(DeleteBehavior.Restrict);
            e.ToTable(t =>
            {
                t.HasCheckConstraint("CK_QualityIncidents_Severity", "[Severity] IN ('Low','Medium','High','Critical')");
                t.HasCheckConstraint("CK_QualityIncidents_Status", "[Status] IN ('Open','Investigating','Resolved')");
            });
        });

        b.Entity<MaintenanceEvent>(e =>
        {
            e.Property(x => x.Id).ValueGeneratedNever();
            e.Property(x => x.ErrorCode).HasMaxLength(8);
            e.Property(x => x.Description).HasMaxLength(256);
            e.Property(x => x.Resolution).HasMaxLength(256);
            e.HasIndex(x => new { x.EquipmentId, x.OccurredAtUtc });
            e.HasOne(x => x.Equipment).WithMany().HasForeignKey(x => x.EquipmentId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.DowntimeEvent).WithMany().HasForeignKey(x => x.DowntimeEventId).OnDelete(DeleteBehavior.Restrict);
        });
    }

    private sealed class UtcConverter() : ValueConverter<DateTime, DateTime>(
        v => EnsureUtc(v),
        v => DateTime.SpecifyKind(v, DateTimeKind.Utc));

    private static DateTime EnsureUtc(DateTime value) => value.Kind == DateTimeKind.Utc
        ? value
        : throw new InvalidOperationException("Only UTC DateTime values may be persisted.");
}
