using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace OpsPilot.Api.Data.Migrations
{
    /// <inheritdoc />
    public partial class InitialSchema : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "DowntimeReasons",
                columns: table => new
                {
                    Code = table.Column<string>(type: "nvarchar(32)", maxLength: 32, nullable: false),
                    Name = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    Category = table.Column<string>(type: "nvarchar(32)", maxLength: 32, nullable: false),
                    IsPlanned = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_DowntimeReasons", x => x.Code);
                });

            migrationBuilder.CreateTable(
                name: "ProductionLines",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    Code = table.Column<string>(type: "nvarchar(8)", maxLength: 8, nullable: false),
                    Name = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    Department = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    NominalRatePerHour = table.Column<int>(type: "int", nullable: false),
                    IsActive = table.Column<bool>(type: "bit", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ProductionLines", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "Equipment",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    LineId = table.Column<int>(type: "int", nullable: false),
                    EquipmentCode = table.Column<string>(type: "nvarchar(32)", maxLength: 32, nullable: false),
                    Name = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    EquipmentType = table.Column<string>(type: "nvarchar(32)", maxLength: 32, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Equipment", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Equipment_ProductionLines_LineId",
                        column: x => x.LineId,
                        principalTable: "ProductionLines",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "ProductionRecords",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("SqlServer:Identity", "1, 1"),
                    LineId = table.Column<int>(type: "int", nullable: false),
                    PeriodStartUtc = table.Column<DateTime>(type: "datetime2(0)", nullable: false),
                    PlannedQuantity = table.Column<int>(type: "int", nullable: false),
                    ProducedQuantity = table.Column<int>(type: "int", nullable: false),
                    DefectiveQuantity = table.Column<int>(type: "int", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ProductionRecords", x => x.Id);
                    table.CheckConstraint("CK_ProductionRecords_Quantities", "[PlannedQuantity] >= 0 AND [ProducedQuantity] >= 0 AND [DefectiveQuantity] >= 0 AND [DefectiveQuantity] <= [ProducedQuantity]");
                    table.ForeignKey(
                        name: "FK_ProductionRecords_ProductionLines_LineId",
                        column: x => x.LineId,
                        principalTable: "ProductionLines",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "QualityIncidents",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false),
                    LineId = table.Column<int>(type: "int", nullable: false),
                    OccurredAtUtc = table.Column<DateTime>(type: "datetime2(0)", nullable: false),
                    Category = table.Column<string>(type: "nvarchar(64)", maxLength: 64, nullable: false),
                    Severity = table.Column<string>(type: "nvarchar(16)", maxLength: 16, nullable: false),
                    Status = table.Column<string>(type: "nvarchar(16)", maxLength: 16, nullable: false),
                    Description = table.Column<string>(type: "nvarchar(256)", maxLength: 256, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_QualityIncidents", x => x.Id);
                    table.CheckConstraint("CK_QualityIncidents_Severity", "[Severity] IN ('Low','Medium','High','Critical')");
                    table.CheckConstraint("CK_QualityIncidents_Status", "[Status] IN ('Open','Investigating','Resolved')");
                    table.ForeignKey(
                        name: "FK_QualityIncidents_ProductionLines_LineId",
                        column: x => x.LineId,
                        principalTable: "ProductionLines",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "DowntimeEvents",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false),
                    LineId = table.Column<int>(type: "int", nullable: false),
                    EquipmentId = table.Column<int>(type: "int", nullable: true),
                    StartTimeUtc = table.Column<DateTime>(type: "datetime2(0)", nullable: false),
                    EndTimeUtc = table.Column<DateTime>(type: "datetime2(0)", nullable: false),
                    DurationMinutes = table.Column<int>(type: "int", nullable: false),
                    ReasonCode = table.Column<string>(type: "nvarchar(32)", maxLength: 32, nullable: false),
                    Description = table.Column<string>(type: "nvarchar(256)", maxLength: 256, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_DowntimeEvents", x => x.Id);
                    table.CheckConstraint("CK_DowntimeEvents_Duration", "[DurationMinutes] = DATEDIFF(minute, [StartTimeUtc], [EndTimeUtc])");
                    table.CheckConstraint("CK_DowntimeEvents_Interval", "[EndTimeUtc] > [StartTimeUtc]");
                    table.ForeignKey(
                        name: "FK_DowntimeEvents_DowntimeReasons_ReasonCode",
                        column: x => x.ReasonCode,
                        principalTable: "DowntimeReasons",
                        principalColumn: "Code",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_DowntimeEvents_Equipment_EquipmentId",
                        column: x => x.EquipmentId,
                        principalTable: "Equipment",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_DowntimeEvents_ProductionLines_LineId",
                        column: x => x.LineId,
                        principalTable: "ProductionLines",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "MaintenanceEvents",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false),
                    EquipmentId = table.Column<int>(type: "int", nullable: false),
                    DowntimeEventId = table.Column<int>(type: "int", nullable: true),
                    OccurredAtUtc = table.Column<DateTime>(type: "datetime2(0)", nullable: false),
                    ErrorCode = table.Column<string>(type: "nvarchar(8)", maxLength: 8, nullable: true),
                    Description = table.Column<string>(type: "nvarchar(256)", maxLength: 256, nullable: false),
                    Resolution = table.Column<string>(type: "nvarchar(256)", maxLength: 256, nullable: false),
                    DurationMinutes = table.Column<int>(type: "int", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MaintenanceEvents", x => x.Id);
                    table.ForeignKey(
                        name: "FK_MaintenanceEvents_DowntimeEvents_DowntimeEventId",
                        column: x => x.DowntimeEventId,
                        principalTable: "DowntimeEvents",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_MaintenanceEvents_Equipment_EquipmentId",
                        column: x => x.EquipmentId,
                        principalTable: "Equipment",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateIndex(
                name: "IX_DowntimeEvents_EquipmentId",
                table: "DowntimeEvents",
                column: "EquipmentId");

            migrationBuilder.CreateIndex(
                name: "IX_DowntimeEvents_LineId_StartTimeUtc",
                table: "DowntimeEvents",
                columns: new[] { "LineId", "StartTimeUtc" })
                .Annotation("SqlServer:Include", new[] { "EndTimeUtc", "ReasonCode" });

            migrationBuilder.CreateIndex(
                name: "IX_DowntimeEvents_ReasonCode",
                table: "DowntimeEvents",
                column: "ReasonCode");

            migrationBuilder.CreateIndex(
                name: "IX_Equipment_EquipmentCode",
                table: "Equipment",
                column: "EquipmentCode",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Equipment_LineId",
                table: "Equipment",
                column: "LineId");

            migrationBuilder.CreateIndex(
                name: "IX_MaintenanceEvents_DowntimeEventId",
                table: "MaintenanceEvents",
                column: "DowntimeEventId");

            migrationBuilder.CreateIndex(
                name: "IX_MaintenanceEvents_EquipmentId_OccurredAtUtc",
                table: "MaintenanceEvents",
                columns: new[] { "EquipmentId", "OccurredAtUtc" });

            migrationBuilder.CreateIndex(
                name: "IX_ProductionLines_Code",
                table: "ProductionLines",
                column: "Code",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_ProductionRecords_LineId_PeriodStartUtc",
                table: "ProductionRecords",
                columns: new[] { "LineId", "PeriodStartUtc" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_ProductionRecords_PeriodStartUtc",
                table: "ProductionRecords",
                column: "PeriodStartUtc");

            migrationBuilder.CreateIndex(
                name: "IX_QualityIncidents_LineId_OccurredAtUtc",
                table: "QualityIncidents",
                columns: new[] { "LineId", "OccurredAtUtc" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "MaintenanceEvents");

            migrationBuilder.DropTable(
                name: "ProductionRecords");

            migrationBuilder.DropTable(
                name: "QualityIncidents");

            migrationBuilder.DropTable(
                name: "DowntimeEvents");

            migrationBuilder.DropTable(
                name: "DowntimeReasons");

            migrationBuilder.DropTable(
                name: "Equipment");

            migrationBuilder.DropTable(
                name: "ProductionLines");
        }
    }
}
