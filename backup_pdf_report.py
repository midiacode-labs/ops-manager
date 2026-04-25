"""
Gerador de relatório de evidências de backup em PDF.
Utiliza reportlab para produzir o documento oficial com identidade Midiacode.
"""

import io
import os
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import HRFlowable

# ── Paleta ───────────────────────────────────────────────────────────────────────

BLUE = colors.HexColor("#0067ff")
DARK = colors.HexColor("#0f172a")
SLATE = colors.HexColor("#475569")
LIGHT_GRAY = colors.HexColor("#f1f5f9")
BORDER_GRAY = colors.HexColor("#e2e8f0")
SUCCESS_BG = colors.HexColor("#dcfce7")
SUCCESS_FG = colors.HexColor("#166534")
ERROR_BG = colors.HexColor("#fee2e2")
ERROR_FG = colors.HexColor("#991b1b")
WARN_BG = colors.HexColor("#fef3c7")
WARN_FG = colors.HexColor("#92400e")

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

LOGO_PATH = os.path.join(os.path.dirname(__file__), "logo_midiacode_h.png")

# ── Estilos ───────────────────────────────────────────────────────────────────────


def _build_styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Normal"],
            fontSize=20,
            fontName="Helvetica-Bold",
            textColor=DARK,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontSize=9,
            fontName="Helvetica",
            textColor=SLATE,
            spaceAfter=2,
        ),
        "section": ParagraphStyle(
            "section",
            parent=base["Normal"],
            fontSize=11,
            fontName="Helvetica-Bold",
            textColor=DARK,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "label": ParagraphStyle(
            "label",
            parent=base["Normal"],
            fontSize=8,
            fontName="Helvetica-Bold",
            textColor=SLATE,
            spaceAfter=1,
        ),
        "value": ParagraphStyle(
            "value",
            parent=base["Normal"],
            fontSize=9,
            fontName="Helvetica",
            textColor=DARK,
        ),
        "mono": ParagraphStyle(
            "mono",
            parent=base["Normal"],
            fontSize=8,
            fontName="Courier",
            textColor=DARK,
            wordWrap="CJK",
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["Normal"],
            fontSize=7,
            fontName="Helvetica",
            textColor=SLATE,
            alignment=TA_CENTER,
        ),
        "badge_ok": ParagraphStyle(
            "badge_ok",
            parent=base["Normal"],
            fontSize=8,
            fontName="Helvetica-Bold",
            textColor=SUCCESS_FG,
        ),
        "badge_error": ParagraphStyle(
            "badge_error",
            parent=base["Normal"],
            fontSize=8,
            fontName="Helvetica-Bold",
            textColor=ERROR_FG,
        ),
        "badge_warn": ParagraphStyle(
            "badge_warn",
            parent=base["Normal"],
            fontSize=8,
            fontName="Helvetica-Bold",
            textColor=WARN_FG,
        ),
        "table_header": ParagraphStyle(
            "table_header",
            parent=base["Normal"],
            fontSize=8,
            fontName="Helvetica-Bold",
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            parent=base["Normal"],
            fontSize=7,
            fontName="Helvetica",
            textColor=DARK,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
        "table_cell_left": ParagraphStyle(
            "table_cell_left",
            parent=base["Normal"],
            fontSize=7,
            fontName="Courier",
            textColor=DARK,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────────


def _fmt_dt(raw: str | None) -> str:
    if not raw:
        return "—"
    try:
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized).astimezone(timezone.utc)
        return dt.strftime("%d/%m/%Y %H:%M UTC")
    except Exception:
        return raw or "—"


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


def _status_label(status: str) -> str:
    mapping = {
        "ok": "Backup disponível",
        "collected": "Backup disponível",
        "partial": "Dados parciais",
        "error": "Erro na coleta",
    }
    return mapping.get(status, "Desconhecido")


def _status_style_key(status: str) -> str:
    if status in ("ok", "collected"):
        return "badge_ok"
    if status == "error":
        return "badge_error"
    return "badge_warn"


def _kv_table(rows: list[tuple[str, str]], styles: dict) -> Table:
    """Renders a two-column key-value table."""
    data = [
        [
            Paragraph(k, styles["label"]),
            Paragraph(v, styles["mono"]),
        ]
        for k, v in rows
    ]
    t = Table(data, colWidths=[4 * cm, CONTENT_W - 4 * cm])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, LIGHT_GRAY]),
                ("LINEBELOW", (0, -1), (-1, -1), 0.3, BORDER_GRAY),
            ]
        )
    )
    return t


def _metric_table(metrics: list[tuple[str, str]], styles: dict) -> Table:
    """Renders a horizontal metrics summary row."""
    headers = [Paragraph(label, styles["label"]) for label, _ in metrics]
    values = [Paragraph(val, styles["section"]) for _, val in metrics]
    col_w = CONTENT_W / len(metrics)
    t = Table([headers, values], colWidths=[col_w] * len(metrics))
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY),
                ("BACKGROUND", (0, 1), (-1, 1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER_GRAY),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


# ── Seções do relatório ───────────────────────────────────────────────────────────


def _build_opensearch_section(report: dict, styles: dict) -> list:
    """Builds the flowables for an OpenSearch backup resource."""
    elements: list = []

    evidence = report.get("alternative_snapshot_evidence", {}) or {}
    snapshot_api = evidence.get("snapshot_api", {}) or {}
    domain_status = evidence.get("domain_status", {}) or {}
    latest_backup = report.get("latest_backup")
    snap_details = snapshot_api.get("latest_snapshot") or {}
    resource_arn = report.get("resource_arn", "—")
    status = report.get("status", "unknown")
    domain_name = domain_status.get("domain_name") or "OpenSearch"

    # Cabeçalho do recurso
    status_txt = _status_label(status)
    style_key = _status_style_key(status)
    header_data = [
        [
            Paragraph(f"OpenSearch — {domain_name}", styles["section"]),
            Paragraph(status_txt, styles[style_key]),
        ]
    ]
    header_t = Table(
        header_data, colWidths=[CONTENT_W * 0.75, CONTENT_W * 0.25]
    )
    header_t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(header_t)
    elements.append(Spacer(1, 0.2 * cm))

    # ARN
    elements.append(Paragraph("ARN do Recurso", styles["label"]))
    elements.append(Paragraph(resource_arn, styles["mono"]))
    elements.append(Spacer(1, 0.3 * cm))

    # Coleta e estratégia
    elements.append(Paragraph("Coleta e Estratégia", styles["section"]))
    elements.append(
        _kv_table(
            [
                ("Coletado em", _fmt_dt(report.get("collected_at"))),
                ("Serviço de Backup", report.get("backup_service") or "—"),
                ("Estratégia", report.get("collection_strategy") or "—"),
            ],
            styles,
        )
    )
    elements.append(Spacer(1, 0.3 * cm))

    # Domínio
    endpoint_url = (
        domain_status.get("endpoint_url")
        or domain_status.get("endpoint")
        or "—"
    )
    endpoints_val = domain_status.get("endpoints")
    if isinstance(endpoints_val, dict):
        endpoints_str = ", ".join(str(v) for v in endpoints_val.values())
    elif endpoints_val:
        endpoints_str = str(endpoints_val)
    else:
        endpoints_str = "—"

    elements.append(Paragraph("Domínio OpenSearch", styles["section"]))
    elements.append(
        _kv_table(
            [
                ("Nome", domain_status.get("domain_name") or "—"),
                ("Versão", domain_status.get("engine_version") or "—"),
                ("ARN", domain_status.get("arn") or "—"),
                ("Endpoint", endpoint_url),
                ("Endpoints adicionais", endpoints_str),
                ("Criado", "Sim" if domain_status.get("created") else "Não"),
                ("Excluído", "Sim" if domain_status.get("deleted") else "Não"),
                (
                    "Em processamento",
                    "Sim" if domain_status.get("processing") else "Não",
                ),
            ],
            styles,
        )
    )
    elements.append(Spacer(1, 0.3 * cm))

    # Repositórios
    repos = snapshot_api.get("repositories") or []
    elements.append(Paragraph("Repositórios de Snapshots", styles["section"]))
    elements.append(
        _kv_table(
            [
                (
                    "Repositórios disponíveis",
                    ", ".join(repos) if repos else "—",
                ),
                (
                    "Repositório selecionado",
                    snapshot_api.get("selected_repository") or "—",
                ),
                (
                    "Total de snapshots",
                    str(snapshot_api.get("snapshots_found") or "—"),
                ),
            ],
            styles,
        )
    )
    elements.append(Spacer(1, 0.3 * cm))

    # Último snapshot
    elements.append(Paragraph("Último Snapshot", styles["section"]))
    if latest_backup or snap_details:
        snap_id = (
            latest_backup.get("snapshot") if latest_backup
            else snap_details.get("snapshot") or "—"
        )
        snap_state = (
            latest_backup.get("state") if latest_backup
            else snap_details.get("state") or "—"
        )
        snap_start = (
            latest_backup.get("start_time") if latest_backup
            else snap_details.get("start_time")
        )
        snap_end = (
            latest_backup.get("end_time") if latest_backup
            else snap_details.get("end_time")
        )
        snap_source = latest_backup.get("source") if latest_backup else "—"
        snap_repo = latest_backup.get("repository") if latest_backup else "—"
        snap_indices_count = snap_details.get("indices_count") or "—"

        t_s = snap_details.get("start_time_in_millis")
        t_e = snap_details.get("end_time_in_millis")
        duration_str = f"{t_e - t_s} ms" if (t_s and t_e) else "—"

        elements.append(
            _kv_table(
                [
                    ("ID do Snapshot", snap_id or "—"),
                    ("Estado", snap_state or "—"),
                    ("Fonte", snap_source),
                    ("Repositório", snap_repo),
                    ("Início", _fmt_dt(snap_start)),
                    ("Fim", _fmt_dt(snap_end)),
                    ("Duração", duration_str),
                    ("Índices cobertos", str(snap_indices_count)),
                ],
                styles,
            )
        )

        # Índices com backup
        indices_list = snap_details.get("indices")
        if isinstance(indices_list, list) and indices_list:
            elements.append(Spacer(1, 0.3 * cm))
            elements.append(
                Paragraph(
                    f"Índices com Backup ({len(indices_list)} índices)",
                    styles["section"],
                )
            )
            sorted_indices = sorted(indices_list)
            # 3-column grid layout
            col_w = CONTENT_W / 3
            chunk_size = 3
            idx_rows = [
                sorted_indices[i: i + chunk_size]
                for i in range(0, len(sorted_indices), chunk_size)
            ]
            # Pad last row
            if idx_rows and len(idx_rows[-1]) < chunk_size:
                idx_rows[-1] += [""] * (chunk_size - len(idx_rows[-1]))

            tbl_data = [
                [Paragraph(cell, styles["mono"]) for cell in row]
                for row in idx_rows
            ]
            idx_tbl = Table(tbl_data, colWidths=[col_w] * chunk_size)
            idx_tbl.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, LIGHT_GRAY]),
                        ("LINEBELOW", (0, -1), (-1, -1), 0.3, BORDER_GRAY),
                    ]
                )
            )
            elements.append(idx_tbl)
    else:
        elements.append(
            Paragraph("Nenhum snapshot disponível.", styles["value"])
        )

    # Amostras de snapshots
    sample_snapshots = snapshot_api.get("sample_snapshots") or []
    if sample_snapshots:
        elements.append(Spacer(1, 0.4 * cm))
        elements.append(
            Paragraph(
                f"Amostras de Snapshots ({len(sample_snapshots)} registros)",
                styles["section"],
            )
        )
        col_defs = [
            ("Snapshot", CONTENT_W * 0.30),
            ("Estado", CONTENT_W * 0.10),
            ("Início", CONTENT_W * 0.17),
            ("Duração", CONTENT_W * 0.10),
            ("Índices", CONTENT_W * 0.08),
            ("Shards OK", CONTENT_W * 0.09),
            ("Falhas", CONTENT_W * 0.08),
            ("Versão", CONTENT_W * 0.08),
        ]
        col_labels = [c[0] for c in col_defs]
        col_widths = [c[1] for c in col_defs]

        tbl_data = [[Paragraph(h, styles["table_header"]) for h in col_labels]]
        for s in sample_snapshots:
            t_s2 = s.get("start_time_in_millis")
            t_e2 = s.get("end_time_in_millis")
            dur2 = f"{t_e2 - t_s2} ms" if (t_s2 and t_e2) else "—"
            shards = s.get("shards") or {}
            tbl_data.append(
                [
                    Paragraph(s.get("snapshot", "—"), styles["table_cell_left"]),
                    Paragraph(s.get("state", "—"), styles["table_cell"]),
                    Paragraph(_fmt_dt(s.get("start_time")), styles["table_cell"]),
                    Paragraph(dur2, styles["table_cell"]),
                    Paragraph(
                        str(len(s.get("indices") or [])), styles["table_cell"]
                    ),
                    Paragraph(
                        str(shards.get("successful", "—")), styles["table_cell"]
                    ),
                    Paragraph(
                        str(len(s.get("failures") or [])), styles["table_cell"]
                    ),
                    Paragraph(s.get("version", "—"), styles["table_cell"]),
                ]
            )

        snap_tbl = Table(tbl_data, colWidths=col_widths, repeatRows=1)
        snap_tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), DARK),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
                    ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER_GRAY),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        elements.append(snap_tbl)

    # Erros
    api_error = snapshot_api.get("error")
    domain_error = evidence.get("domain_error")
    if api_error or domain_error:
        elements.append(Spacer(1, 0.3 * cm))
        elements.append(Paragraph("Erros de Coleta", styles["section"]))
        if domain_error:
            msg = (
                domain_error.get("message", str(domain_error))
                if isinstance(domain_error, dict)
                else str(domain_error)
            )
            elements.append(Paragraph(f"Domínio: {msg}", styles["badge_error"]))
        if api_error:
            msg = (
                api_error.get("message", str(api_error))
                if isinstance(api_error, dict)
                else str(api_error)
            )
            elements.append(Paragraph(f"API de Snapshots: {msg}", styles["badge_error"]))

    return elements


def _build_generic_section(report: dict, styles: dict) -> list:
    """Builds flowables for a non-OpenSearch backup resource."""
    elements: list = []
    resource_type = report.get("resource_type", "Recurso").upper()
    resource_arn = report.get("resource_arn", "—")
    status = report.get("status", "unknown")
    latest_backup = report.get("latest_backup")

    header_data = [
        [
            Paragraph(f"{resource_type}", styles["section"]),
            Paragraph(_status_label(status), styles[_status_style_key(status)]),
        ]
    ]
    header_t = Table(
        header_data, colWidths=[CONTENT_W * 0.75, CONTENT_W * 0.25]
    )
    header_t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(header_t)
    elements.append(Spacer(1, 0.2 * cm))
    elements.append(Paragraph("ARN do Recurso", styles["label"]))
    elements.append(Paragraph(resource_arn, styles["mono"]))

    if latest_backup:
        elements.append(Spacer(1, 0.3 * cm))
        elements.append(Paragraph("Último Backup", styles["section"]))
        kv = [
            (k, str(v) if v is not None else "—")
            for k, v in latest_backup.items()
        ]
        elements.append(_kv_table(kv, styles))

    error = report.get("error")
    if error:
        elements.append(Spacer(1, 0.2 * cm))
        msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        elements.append(Paragraph(f"Erro: {msg}", styles["badge_error"]))

    return elements


def _build_rds_section(report: dict, styles: dict) -> list:
    """Builds flowables for RDS instance/cluster backup evidence."""
    elements: list = []
    resource_type = (report.get("resource_type") or "RDS").upper()
    resource_arn = report.get("resource_arn", "—")
    status = report.get("status", "unknown")
    evidence = report.get("rds_snapshot_evidence", {}) or {}
    snapshot_api = evidence.get("snapshot_api", {}) or {}
    resource_status = evidence.get("resource_status", {}) or {}

    header_data = [
        [
            Paragraph(f"{resource_type}", styles["section"]),
            Paragraph(_status_label(status), styles[_status_style_key(status)]),
        ]
    ]
    header_t = Table(
        header_data, colWidths=[CONTENT_W * 0.75, CONTENT_W * 0.25]
    )
    header_t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(header_t)
    elements.append(Spacer(1, 0.2 * cm))

    elements.append(Paragraph("ARN do Recurso", styles["label"]))
    elements.append(Paragraph(resource_arn, styles["mono"]))
    elements.append(Spacer(1, 0.3 * cm))

    elements.append(Paragraph("Coleta e Estratégia", styles["section"]))
    elements.append(
        _kv_table(
            [
                ("Coletado em", _fmt_dt(report.get("collected_at"))),
                ("Serviço de Backup", report.get("backup_service") or "—"),
                ("Estratégia", report.get("collection_strategy") or "—"),
            ],
            styles,
        )
    )
    elements.append(Spacer(1, 0.3 * cm))

    encrypted_label = "Sim" if resource_status.get("storage_encrypted") else "Não"
    deletion_protection_label = (
        "Sim" if resource_status.get("deletion_protection") else "Não"
    )
    elements.append(Paragraph("Recurso RDS", styles["section"]))
    elements.append(
        _kv_table(
            [
                (
                    "Tipo do recurso",
                    resource_status.get("resource_type")
                    or evidence.get("resource_kind")
                    or "—",
                ),
                (
                    "Identificador",
                    evidence.get("resource_identifier") or "—",
                ),
                ("Engine", resource_status.get("engine") or "—"),
                ("Versão do engine", resource_status.get("engine_version") or "—"),
                (
                    "Retenção de backup (dias)",
                    str(resource_status.get("backup_retention_period") or "—"),
                ),
                (
                    "Janela preferencial",
                    resource_status.get("preferred_backup_window") or "—",
                ),
                (
                    "Último ponto restaurável",
                    _fmt_dt(resource_status.get("latest_restorable_time")),
                ),
                ("Criptografado", encrypted_label),
                ("Deletion protection", deletion_protection_label),
            ],
            styles,
        )
    )
    elements.append(Spacer(1, 0.3 * cm))

    latest_snapshot = snapshot_api.get("latest_snapshot") or {}
    elements.append(Paragraph("Snapshots Automatizados", styles["section"]))
    elements.append(
        _kv_table(
            [
                ("Snapshots encontrados", str(snapshot_api.get("snapshots_found") or 0)),
                (
                    "Snapshot mais recente",
                    latest_snapshot.get("snapshot_identifier") or "—",
                ),
                ("Status", latest_snapshot.get("status") or "—"),
                ("Tipo", latest_snapshot.get("snapshot_type") or "—"),
                (
                    "Criado em",
                    _fmt_dt(latest_snapshot.get("snapshot_create_time")),
                ),
                ("Engine", latest_snapshot.get("engine") or "—"),
                (
                    "Versão do engine",
                    latest_snapshot.get("engine_version") or "—",
                ),
                (
                    "Criptografado",
                    "Sim" if latest_snapshot.get("encrypted") else "Não",
                ),
            ],
            styles,
        )
    )

    resource_error = evidence.get("resource_error")
    snapshot_error = snapshot_api.get("error")
    if resource_error or snapshot_error:
        elements.append(Spacer(1, 0.2 * cm))
        elements.append(Paragraph("Erros de Coleta", styles["section"]))
        if resource_error:
            msg = (
                resource_error.get("message", str(resource_error))
                if isinstance(resource_error, dict)
                else str(resource_error)
            )
            elements.append(Paragraph(f"Metadados do recurso: {msg}", styles["badge_error"]))
        if snapshot_error:
            msg = (
                snapshot_error.get("message", str(snapshot_error))
                if isinstance(snapshot_error, dict)
                else str(snapshot_error)
            )
            elements.append(Paragraph(f"Snapshots: {msg}", styles["badge_error"]))

    return elements


def _build_dynamodb_section(report: dict, styles: dict) -> list:
    """Builds flowables for DynamoDB backup evidence."""
    elements: list = []
    resource_arn = report.get("resource_arn", "—")
    status = report.get("status", "unknown")
    latest_backup = report.get("latest_backup") or {}
    evidence = report.get("dynamodb_backup_evidence", {}) or {}
    table_description = evidence.get("table_description", {}) or {}
    continuous_backup = evidence.get("continuous_backup_description", {}) or {}
    native_summary = evidence.get("native_backup_summary", {}) or {}

    header_data = [
        [
            Paragraph("DYNAMODB", styles["section"]),
            Paragraph(_status_label(status), styles[_status_style_key(status)]),
        ]
    ]
    header_t = Table(header_data, colWidths=[CONTENT_W * 0.75, CONTENT_W * 0.25])
    header_t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(header_t)
    elements.append(Spacer(1, 0.2 * cm))

    elements.append(Paragraph("ARN do Recurso", styles["label"]))
    elements.append(Paragraph(resource_arn, styles["mono"]))
    elements.append(Spacer(1, 0.3 * cm))

    elements.append(Paragraph("Coleta e Estratégia", styles["section"]))
    elements.append(
        _kv_table(
            [
                ("Coletado em", _fmt_dt(report.get("collected_at"))),
                ("Serviço de Backup", report.get("backup_service") or "—"),
                ("Estratégia", report.get("collection_strategy") or "—"),
                ("Fonte do último backup", latest_backup.get("source") or "—"),
            ],
            styles,
        )
    )
    elements.append(Spacer(1, 0.3 * cm))

    elements.append(Paragraph("Tabela DynamoDB", styles["section"]))
    elements.append(
        _kv_table(
            [
                ("Nome", table_description.get("table_name") or evidence.get("table_name") or "—"),
                ("Status da tabela", table_description.get("table_status") or "—"),
                ("Criada em", _fmt_dt(table_description.get("creation_date_time"))),
                ("Itens", str(table_description.get("item_count") or 0)),
                ("Tamanho (bytes)", str(table_description.get("table_size_bytes") or 0)),
                ("Modo de cobrança", table_description.get("billing_mode") or "—"),
                ("Criptografia (SSE)", table_description.get("sse_status") or "—"),
                ("Tipo SSE", table_description.get("sse_type") or "—"),
            ],
            styles,
        )
    )
    elements.append(Spacer(1, 0.3 * cm))

    elements.append(Paragraph("Backup Contínuo (PITR)", styles["section"]))
    elements.append(
        _kv_table(
            [
                (
                    "ContinuousBackupsStatus",
                    continuous_backup.get("continuous_backups_status") or "—",
                ),
                (
                    "PointInTimeRecoveryStatus",
                    continuous_backup.get("point_in_time_recovery_status") or "—",
                ),
                (
                    "EarliestRestorableDateTime",
                    _fmt_dt(continuous_backup.get("earliest_restorable_datetime")),
                ),
                (
                    "LatestRestorableDateTime",
                    _fmt_dt(continuous_backup.get("latest_restorable_datetime")),
                ),
            ],
            styles,
        )
    )
    elements.append(Spacer(1, 0.3 * cm))

    elements.append(Paragraph("Último Backup Selecionado", styles["section"]))
    elements.append(
        _kv_table(
            [
                (
                    "Backup ARN / Recovery Point ARN",
                    latest_backup.get("backup_arn_or_recovery_point_arn") or "—",
                ),
                ("Status", latest_backup.get("status") or "—"),
                ("Tipo", latest_backup.get("backup_type") or "—"),
                ("Criado em", _fmt_dt(latest_backup.get("creation_date"))),
            ],
            styles,
        )
    )

    elements.append(Spacer(1, 0.3 * cm))
    elements.append(Paragraph("Backups Nativos DynamoDB", styles["section"]))
    latest_native = native_summary.get("latest_backup") or {}
    elements.append(
        _kv_table(
            [
                ("Backups encontrados", str(native_summary.get("backups_found") or 0)),
                (
                    "Último backup nativo",
                    latest_native.get("backup_name")
                    or latest_native.get("backup_arn_or_recovery_point_arn")
                    or "—",
                ),
                ("Status último nativo", latest_native.get("status") or "—"),
                ("Tipo último nativo", latest_native.get("backup_type") or "—"),
                ("Criado em (nativo)", _fmt_dt(latest_native.get("creation_date"))),
            ],
            styles,
        )
    )

    collection_errors = evidence.get("collection_errors") or []
    if collection_errors:
        elements.append(Spacer(1, 0.2 * cm))
        elements.append(Paragraph("Erros de Coleta", styles["section"]))
        for error in collection_errors:
            stage = error.get("stage") or error.get("type") or "coleta"
            message = error.get("message") or "Erro não identificado."
            elements.append(Paragraph(f"{stage}: {message}", styles["badge_error"]))

    top_level_error = report.get("error")
    if top_level_error:
        elements.append(Spacer(1, 0.2 * cm))
        msg = (
            top_level_error.get("message", str(top_level_error))
            if isinstance(top_level_error, dict)
            else str(top_level_error)
        )
        elements.append(Paragraph(f"Erro: {msg}", styles["badge_error"]))

    return elements


# ── Página com cabeçalho e rodapé ─────────────────────────────────────────────────


class _BackupDocTemplate(BaseDocTemplate):
    """Custom doc template that injects header/footer on every page."""

    def __init__(self, buf: io.BytesIO, system_url: str, generated_at: str):
        super().__init__(
            buf,
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN + 2.5 * cm,
            bottomMargin=MARGIN + 1.5 * cm,
        )
        self._system_url = system_url
        self._generated_at = generated_at
        self._styles = _build_styles()
        self._setup_templates()

    def _setup_templates(self) -> None:
        frame = Frame(
            MARGIN,
            MARGIN + 1.5 * cm,
            PAGE_W - 2 * MARGIN,
            PAGE_H - 2 * MARGIN - 2.5 * cm - 1.5 * cm,
            id="main",
        )
        self.addPageTemplates(
            [PageTemplate(id="main", frames=[frame], onPage=self._draw_chrome)]
        )

    def _draw_chrome(self, canvas, doc) -> None:
        canvas.saveState()
        self._draw_header(canvas)
        self._draw_footer(canvas, doc)
        canvas.restoreState()

    def _draw_header(self, canvas) -> None:
        # Logo
        if os.path.exists(LOGO_PATH):
            logo_h = 1.0 * cm
            logo_w = logo_h * 5.5  # aprox. aspect ratio 5.5:1
            canvas.drawImage(
                LOGO_PATH,
                MARGIN,
                PAGE_H - MARGIN - logo_h,
                width=logo_w,
                height=logo_h,
                preserveAspectRatio=True,
                mask="auto",
            )

        # Título alinhado à direita
        canvas.setFont("Helvetica-Bold", 14)
        canvas.setFillColor(DARK)
        canvas.drawRightString(
            PAGE_W - MARGIN,
            PAGE_H - MARGIN - 0.5 * cm,
            "Relatório de Evidências de Backup",
        )
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(SLATE)
        canvas.drawRightString(
            PAGE_W - MARGIN,
            PAGE_H - MARGIN - 0.9 * cm,
            f"Gerado em: {self._generated_at}",
        )

        # Linha divisória
        canvas.setStrokeColor(BORDER_GRAY)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, PAGE_H - MARGIN - 1.3 * cm, PAGE_W - MARGIN, PAGE_H - MARGIN - 1.3 * cm)

    def _draw_footer(self, canvas, doc) -> None:
        y = MARGIN + 0.8 * cm
        canvas.setStrokeColor(BORDER_GRAY)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, y, PAGE_W - MARGIN, y)

        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(SLATE)
        footer_text = (
            f"{self._system_url}  •  {self._generated_at}  •  "
            f"Midiacode — Documento Confidencial  •  Página {doc.page}"
        )
        canvas.drawCentredString(PAGE_W / 2, y - 0.35 * cm, footer_text)


# ── Ponto de entrada público ──────────────────────────────────────────────────────


def generate_pdf(report_data: dict, system_url: str = "") -> bytes:
    """
    Generates the backup evidence report PDF and returns its bytes.

    Args:
        report_data: The dict returned by AwsBackupEvidenceCollector.collect().
        system_url:  The URL of the Ops Manager system shown in the footer.

    Returns:
        Raw bytes of the generated PDF.
    """
    styles = _build_styles()
    generated_at = _fmt_dt(report_data.get("generated_at")) or _now_str()
    reports = report_data.get("reports", [])
    summary = report_data.get("summary", {})
    region = report_data.get("region", "—")

    buf = io.BytesIO()
    doc = _BackupDocTemplate(buf, system_url=system_url, generated_at=generated_at)

    elements: list = []

    # ── Resumo global ────────────────────────────────────────────────────────
    elements.append(Paragraph("Resumo Geral", styles["section"]))
    elements.append(
        _metric_table(
            [
                ("Total de Recursos", str(summary.get("total_resources", 0))),
                ("Com Backup", str(summary.get("resources_with_backup", 0))),
                ("Sem Backup", str(summary.get("resources_without_backup", 0))),
                ("Com Erro", str(summary.get("resources_with_error", 0))),
                ("Região AWS", region),
            ],
            styles,
        )
    )
    elements.append(Spacer(1, 0.5 * cm))

    # ── Recursos ─────────────────────────────────────────────────────────────
    elements.append(
        HRFlowable(
            width=CONTENT_W, thickness=1, color=BLUE, spaceAfter=8
        )
    )

    for i, report in enumerate(reports):
        if i > 0:
            elements.append(Spacer(1, 0.5 * cm))
            elements.append(
                HRFlowable(
                    width=CONTENT_W,
                    thickness=0.5,
                    color=BORDER_GRAY,
                    spaceAfter=8,
                )
            )

        resource_type = (report.get("resource_type") or "").lower()
        if resource_type == "opensearch":
            elements.extend(_build_opensearch_section(report, styles))
        elif resource_type in {"rds", "rds_instance", "rds_cluster"}:
            elements.extend(_build_rds_section(report, styles))
        elif resource_type == "dynamodb":
            elements.extend(_build_dynamodb_section(report, styles))
        else:
            elements.extend(_build_generic_section(report, styles))

    doc.build(elements)
    return buf.getvalue()
