"""
Página de Evidências de Backup
Exibe o relatório dos últimos backups dos recursos AWS monitorados.
"""

import logging
import os
from datetime import datetime, timezone

import streamlit as st
from dotenv import load_dotenv

from auth import display_auth_ui
from backup_evidence_report import AwsBackupEvidenceCollector, BackupResource
from backup_pdf_report import generate_pdf
from app_version import get_app_version

load_dotenv()

LOGGER = logging.getLogger("ops_manager.backup")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    LOGGER.addHandler(_handler)
LOGGER.setLevel(os.getenv("APP_LOG_LEVEL", "INFO").upper())
LOGGER.propagate = False
APP_VERSION = get_app_version()

# ── Autenticação ────────────────────────────────────────────────────────────────

display_auth_ui()

# ── Estilos ─────────────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@500;700;800&display=swap');

    html, body, [class*="css"], [data-testid="stAppViewContainer"] {
        font-family: 'Manrope', sans-serif;
    }

    .ops-page-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 14px;
        margin: 6px 0 20px 0;
        padding: 16px;
        border: 1px solid #e2e8f0;
        border-radius: 16px;
        background:
            radial-gradient(circle at top right, #e2e8f0 0%, transparent 50%),
            linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
    }

    .ops-page-title {
        margin: 0;
        color: #0f172a;
        font-size: 30px;
        font-weight: 800;
        line-height: 1.15;
    }

    .ops-page-subtitle {
        margin-top: 8px;
        color: #475569;
        font-size: 14px;
        max-width: 760px;
    }

    .ops-page-badge {
        background: #0f172a;
        color: #f8fafc;
        border-radius: 999px;
        padding: 6px 12px;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.03em;
        text-transform: uppercase;
        white-space: nowrap;
    }

    .backup-card {
        padding: 0;
        border-radius: 0;
        border: none;
        background: transparent;
        margin-bottom: 8px;
        box-shadow: none;
    }

    .backup-card-title {
        font-size: 15px;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 4px;
    }

    .backup-card-arn {
        font-size: 11px;
        color: #94a3b8;
        font-family: monospace;
        word-break: break-all;
        margin-bottom: 10px;
    }

    .backup-badge {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        padding: 3px 10px;
        font-size: 12px;
        font-weight: 700;
        white-space: nowrap;
    }

    .backup-badge--ok       { color: #166534; background: #dcfce7; border: 1px solid #86efac; }
    .backup-badge--partial  { color: #92400e; background: #fef3c7; border: 1px solid #fcd34d; }
    .backup-badge--error    { color: #991b1b; background: #fee2e2; border: 1px solid #fca5a5; }
    .backup-badge--unsupported { color: #1e3a8a; background: #dbeafe; border: 1px solid #93c5fd; }
    .backup-badge--unknown  { color: #374151; background: #f3f4f6; border: 1px solid #d1d5db; }

    .backup-meta-label {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #64748b;
    }

    .backup-meta-value {
        font-size: 13px;
        color: #0f172a;
        margin-top: 2px;
    }

    .backup-legend {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 8px 0 4px 0;
    }

    .backup-section-title {
        margin: 16px 0 8px 0;
        color: #0f172a;
        font-size: 15px;
        font-weight: 800;
        letter-spacing: 0.01em;
    }

    .backup-help-text {
        margin: 0 0 10px 0;
        color: #64748b;
        font-size: 12px;
    }

    .resource-group-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 14px;
        margin-bottom: 8px;
    }

    .resource-group-title {
        font-size: 20px;
        font-weight: 800;
        color: #0f172a;
        line-height: 1.15;
        margin-bottom: 4px;
    }

    .resource-group-subtitle {
        color: #64748b;
        font-size: 11px;
        font-family: monospace;
        word-break: break-all;
    }

    .resource-divider {
        border: 0;
        border-top: 1px solid #e2e8f0;
        margin: 10px 0 12px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Cabeçalho ────────────────────────────────────────────────────────────────────

st.markdown(
    """
    <div class="ops-page-header">
        <div>
            <h1 class="ops-page-title">Backup</h1>
            <div class="ops-page-subtitle">
                Relatório dos últimos backups e snapshots dos recursos AWS monitorados.
                Os dados são coletados em tempo real via AWS CLI e API de snapshots.
            </div>
        </div>
        <div class="ops-page-badge">Produção</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Helpers ──────────────────────────────────────────────────────────────────────


def _build_resources() -> list[BackupResource]:
    resources: list[BackupResource] = []

    opensearch_arn = os.getenv("OPENSEARCH_RESOURCE_ARN", "").strip()
    if opensearch_arn:
        resources.append(BackupResource(resource_type="opensearch", resource_arn=opensearch_arn))

    rds_account_api_arn = os.getenv("RDS_ACCOUNT_API_RESOURCE_ARN", "").strip()
    if rds_account_api_arn:
        resources.append(
            BackupResource(resource_type="rds_instance", resource_arn=rds_account_api_arn)
        )

    rds_contentcore_api_arn = os.getenv("RDS_CONTENTCORE_API_RESOURCE_ARN", "").strip()
    if rds_contentcore_api_arn:
        resources.append(
            BackupResource(resource_type="rds_cluster", resource_arn=rds_contentcore_api_arn)
        )

    dynamodb_resource_arns_raw = os.getenv("DYNAMODB_RESOURCE_ARNS", "").strip()
    if dynamodb_resource_arns_raw:
        dynamodb_arns = [
            value.strip()
            for value in dynamodb_resource_arns_raw.split(",")
            if value and value.strip()
        ]
    else:
        dynamodb_arns = []

    seen_dynamodb_arns: set[str] = set()
    for dynamodb_arn in dynamodb_arns:
        if dynamodb_arn in seen_dynamodb_arns:
            continue
        seen_dynamodb_arns.add(dynamodb_arn)
        resources.append(BackupResource(resource_type="dynamodb", resource_arn=dynamodb_arn))

    return resources


def _status_badge(status: str) -> str:
    mapping = {
        "ok": ("ok", "✅ Backup disponível"),
        "partial": ("partial", "⚠️ Dados parciais"),
        "error": ("error", "❌ Erro na coleta"),
        "collected": ("ok", "✅ Backup disponível"),
    }
    css_class, label = mapping.get(status, ("unknown", "— Desconhecido"))
    return f'<span class="backup-badge backup-badge--{css_class}">{label}</span>'


def _status_priority(status: str) -> int:
    priority = {
        "error": 0,
        "partial": 1,
        "resource_not_supported_by_aws_backup": 2,
        "ok": 3,
        "collected": 3,
    }
    return priority.get(status, 4)


def _parse_iso_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        normalized = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    except Exception:
        return None


def _get_latest_backup_datetime(report: dict) -> datetime | None:
    latest_backup = report.get("latest_backup") or {}
    resource_type = str(report.get("resource_type") or "").lower()

    candidate_fields: list[str]
    if resource_type == "opensearch":
        candidate_fields = ["start_time"]
    elif resource_type in {"rds", "rds_instance", "rds_cluster"}:
        candidate_fields = ["snapshot_create_time", "creation_date", "start_time"]
    else:
        candidate_fields = ["creation_date", "start_time", "snapshot_create_time"]

    for field in candidate_fields:
        parsed = _parse_iso_datetime(latest_backup.get(field))
        if parsed:
            return parsed
    return None


def _is_stale_backup(report: dict) -> bool:
    backup_datetime = _get_latest_backup_datetime(report)
    if not backup_datetime:
        return False
    return backup_datetime.date() != datetime.now(timezone.utc).date()


def _is_effective_partial(report: dict) -> bool:
    return str(report.get("status") or "") == "partial" or _is_stale_backup(report)


def _build_status_overview(reports: list[dict]) -> str:
    status_counts = {
        "ok": 0,
        "partial": 0,
        "error": 0,
        "unsupported": 0,
        "unknown": 0,
    }

    for report in reports:
        status = str(report.get("status") or "unknown")
        if _is_effective_partial(report):
            status_counts["partial"] += 1
        elif status in {"ok", "collected"}:
            status_counts["ok"] += 1
        elif status == "error":
            status_counts["error"] += 1
        elif status == "resource_not_supported_by_aws_backup":
            status_counts["unsupported"] += 1
        else:
            status_counts["unknown"] += 1

    chips: list[str] = []
    if status_counts["error"]:
        chips.append(
            '<span class="backup-badge backup-badge--error">'
            f'❌ Erro na coleta: {status_counts["error"]}</span>'
        )
    if status_counts["partial"]:
        chips.append(
            '<span class="backup-badge backup-badge--partial">'
            f'⚠️ Dados parciais: {status_counts["partial"]}</span>'
        )
    if status_counts["unsupported"]:
        chips.append(
            '<span class="backup-badge backup-badge--unsupported">'
            f'ℹ️ Não suportado no AWS Backup: {status_counts["unsupported"]}</span>'
        )
    if status_counts["ok"]:
        chips.append(
            '<span class="backup-badge backup-badge--ok">'
            f'✅ Backup disponível: {status_counts["ok"]}</span>'
        )
    if status_counts["unknown"]:
        chips.append(
            '<span class="backup-badge backup-badge--unknown">'
            f'— Status desconhecido: {status_counts["unknown"]}</span>'
        )

    if not chips:
        return ""

    chips_html = "".join(chips)
    return (
        f'<div class="backup-legend">{chips_html}</div>'
        '<p class="backup-help-text">'
        'A listagem está ordenada por criticidade: erros e dados parciais aparecem primeiro.'
        '</p>'
    )


def _format_datetime(raw: str | None) -> str:
    if not raw:
        return "—"
    try:
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized).astimezone(timezone.utc)
        return dt.strftime("%d/%m/%Y %H:%M UTC")
    except Exception:
        return raw


def _render_stale_backup_warning(report: dict, label: str) -> None:
    if not _is_stale_backup(report):
        return

    backup_datetime = _get_latest_backup_datetime(report)
    backup_label = backup_datetime.strftime("%d/%m/%Y") if backup_datetime else "data indisponível"
    today_label = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    st.warning(
        f"⚠️ {label} fora do dia atual (UTC). Último registro: {backup_label}. "
        f"Hoje (UTC): {today_label}."
    )


def _resource_type_label(resource_type: str) -> str:
    labels = {
        "opensearch": "OpenSearch",
        "rds": "RDS",
        "rds_instance": "RDS Instance",
        "rds_cluster": "RDS Cluster",
        "dynamodb": "DynamoDB",
    }
    return labels.get(resource_type.lower(), resource_type.upper())


# ── Coleta ───────────────────────────────────────────────────────────────────────


def _collect_report(resources: list[BackupResource]) -> dict:
    collector = AwsBackupEvidenceCollector(
        resources=resources,
        region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    )
    return collector.collect()


# ── Renderização do relatório ────────────────────────────────────────────────────


def _render_opensearch_report(report: dict) -> None:
    resource_arn = report.get("resource_arn", "")
    status = report.get("status", "unknown")
    latest_backup = report.get("latest_backup")
    evidence = report.get("alternative_snapshot_evidence", {}) or {}
    snapshot_api = evidence.get("snapshot_api", {}) or {}
    domain_status = evidence.get("domain_status", {}) or {}

    with st.container(border=True):
        # Resumo do card
        st.markdown(
            f"""
            <div class="resource-group-header">
                <div>
                    <div class="resource-group-title">
                        🔍 OpenSearch — {domain_status.get("domain_name") or "search-service"}
                    </div>
                    <div class="resource-group-subtitle">{resource_arn}</div>
                </div>
                <div>{_status_badge(status)}</div>
            </div>
            <hr class="resource-divider" />
            """,
            unsafe_allow_html=True,
        )

        _render_stale_backup_warning(report, "Último Snapshot")

        # Métricas rápidas
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown('<div class="backup-meta-label">Motor</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="backup-meta-value">'
                f'{domain_status.get("engine_version") or "—"}</div>',
                unsafe_allow_html=True,
            )

        with col2:
            st.markdown(
                '<div class="backup-meta-label">Último Snapshot</div>',
                unsafe_allow_html=True,
            )
            snap_time = latest_backup.get("start_time") if latest_backup else None
            st.markdown(
                f'<div class="backup-meta-value">{_format_datetime(snap_time)}</div>',
                unsafe_allow_html=True,
            )

        with col3:
            st.markdown(
                '<div class="backup-meta-label">Estado do Snapshot</div>',
                unsafe_allow_html=True,
            )
            snap_state = latest_backup.get("state") if latest_backup else None
            state_label = snap_state or "—"
            if snap_state == "SUCCESS":
                state_label = "✅ SUCCESS"
            elif snap_state:
                state_label = f"⚠️ {snap_state}"
            st.markdown(
                f'<div class="backup-meta-value">{state_label}</div>',
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        with st.expander("Ver detalhes", expanded=False):
            # ── Coleta ──────────────────────────────────────────────────────────
            st.markdown("**Coleta e Estratégia**")
            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                st.markdown(
                    '<div class="backup-meta-label">Coletado em</div>',
                    unsafe_allow_html=True,
                )
                collected = _format_datetime(report.get("collected_at"))
                st.markdown(
                    f'<div class="backup-meta-value">{collected}</div>',
                    unsafe_allow_html=True,
                )
            with cc2:
                st.markdown(
                    '<div class="backup-meta-label">Serviço de Backup</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="backup-meta-value">'
                    f'{report.get("backup_service") or "—"}</div>',
                    unsafe_allow_html=True,
                )
            with cc3:
                st.markdown(
                    '<div class="backup-meta-label">Estratégia</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="backup-meta-value">'
                    f'{report.get("collection_strategy") or "—"}</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("---")

            # ── Domínio ──────────────────────────────────────────────────────────
            st.markdown("**Domínio OpenSearch**")
            dc1, dc2 = st.columns(2)
            with dc1:
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
                st.markdown(
                    f"- **Nome:** `{domain_status.get('domain_name') or '—'}`\n"
                    f"- **Versão:** `{domain_status.get('engine_version') or '—'}`\n"
                    f"- **ARN:** `{domain_status.get('arn') or '—'}`\n"
                    f"- **Endpoint:** `{endpoint_url}`\n"
                    f"- **Endpoints:** `{endpoints_str}`"
                )
            with dc2:
                created = '✅ Sim' if domain_status.get('created') else '❌ Não'
                deleted = '⚠️ Sim' if domain_status.get('deleted') else '✅ Não'
                processing = '⚠️ Sim' if domain_status.get('processing') else '✅ Não'
                st.markdown(
                    f"- **Criado:** {created}\n"
                    f"- **Excluído:** {deleted}\n"
                    f"- **Em processamento:** {processing}"
                )

            st.markdown("---")

            # ── Repositórios ─────────────────────────────────────────────────────
            st.markdown("**Repositórios de Snapshots**")
            repos = snapshot_api.get("repositories") or []
            rc1, rc2, rc3 = st.columns(3)
            with rc1:
                st.markdown(
                    '<div class="backup-meta-label">Repositórios Disponíveis</div>',
                    unsafe_allow_html=True,
                )
                repos_str = ", ".join(f"`{r}`" for r in repos) if repos else "—"
                st.markdown(
                    f'<div class="backup-meta-value">{repos_str}</div>',
                    unsafe_allow_html=True,
                )
            with rc2:
                st.markdown(
                    '<div class="backup-meta-label">Repositório Selecionado</div>',
                    unsafe_allow_html=True,
                )
                selected_repo = snapshot_api.get("selected_repository") or "—"
                st.markdown(
                    f'<div class="backup-meta-value">`{selected_repo}`</div>',
                    unsafe_allow_html=True,
                )
            with rc3:
                st.markdown(
                    '<div class="backup-meta-label">Total de Snapshots</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="backup-meta-value">'
                    f'{snapshot_api.get("snapshots_found") or "—"}</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("---")

            # ── Último snapshot ──────────────────────────────────────────────────
            st.markdown("**Último Snapshot**")
            snap_details = snapshot_api.get("latest_snapshot") or {}
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
                snap_indices = snap_details.get("indices_count") or "—"

                t_start = snap_details.get("start_time_in_millis")
                t_end = snap_details.get("end_time_in_millis")
                duration_str = f"{t_end - t_start} ms" if (t_start and t_end) else "—"

                sc1, sc2, sc3 = st.columns(3)
                with sc1:
                    st.markdown(
                        f"- **ID:** `{snap_id}`\n"
                        f"- **Estado:** `{snap_state}`\n"
                        f"- **Fonte:** `{snap_source}`"
                    )
                with sc2:
                    st.markdown(
                        f"- **Repositório:** `{snap_repo}`\n"
                        f"- **Índices cobertos:** {snap_indices}\n"
                        f"- **Duração:** {duration_str}"
                    )
                with sc3:
                    st.markdown(
                        f"- **Início:** {_format_datetime(snap_start)}\n"
                        f"- **Fim:** {_format_datetime(snap_end)}"
                    )

                indices_list = snap_details.get("indices")
                if isinstance(indices_list, list) and indices_list:
                    st.markdown(
                        f"**Índices com Backup** *({len(indices_list)} índices)*"
                    )
                    cols = st.columns(3)
                    for i, idx in enumerate(sorted(indices_list)):
                        cols[i % 3].markdown(f"- `{idx}`")
            else:
                st.warning("Nenhum snapshot disponível no repositório selecionado.")

            # ── Amostras de snapshots ────────────────────────────────────────────
            sample_snapshots = snapshot_api.get("sample_snapshots") or []
            if sample_snapshots:
                st.markdown("---")
                st.markdown(
                    f"**Amostras de Snapshots** *({len(sample_snapshots)} registros)*"
                )
                import pandas as pd

                rows = []
                for s in sample_snapshots:
                    t_s = s.get("start_time_in_millis")
                    t_e = s.get("end_time_in_millis")
                    dur = f"{t_e - t_s} ms" if (t_s and t_e) else "—"
                    shards = s.get("shards") or {}
                    rows.append({
                        "Snapshot": s.get("snapshot", "—"),
                        "Estado": s.get("state", "—"),
                        "Início": _format_datetime(s.get("start_time")),
                        "Fim": _format_datetime(s.get("end_time")),
                        "Duração": dur,
                        "Índices": len(s.get("indices") or []),
                        "Shards Total": shards.get("total", "—"),
                        "Shards OK": shards.get("successful", "—"),
                        "Shards Falha": shards.get("failed", "—"),
                        "Versão OS": s.get("version", "—"),
                        "Falhas": len(s.get("failures") or []),
                    })
                st.dataframe(
                    pd.DataFrame(rows), use_container_width=True, hide_index=True
                )

            # ── Erros de coleta ──────────────────────────────────────────────────
            api_error = snapshot_api.get("error")
            domain_error = evidence.get("domain_error")
            if api_error or domain_error:
                st.markdown("---")
                st.markdown("**Erros de Coleta**")
                if domain_error:
                    st.error(f"Domínio: {domain_error.get('message', domain_error)}")
                if api_error:
                    st.error(f"API de Snapshots: {api_error.get('message', api_error)}")


def _render_generic_report(report: dict) -> None:
    resource_type = _resource_type_label(report.get("resource_type", ""))
    resource_arn = report.get("resource_arn", "")
    status = report.get("status", "unknown")
    latest_backup = report.get("latest_backup")

    with st.container(border=True):
        st.markdown(
            f"""
            <div class="resource-group-header">
                <div>
                    <div class="resource-group-title">📦 {resource_type}</div>
                    <div class="resource-group-subtitle">{resource_arn}</div>
                </div>
                <div>{_status_badge(status)}</div>
            </div>
            <hr class="resource-divider" />
            """,
            unsafe_allow_html=True,
        )

        _render_stale_backup_warning(report, "Último Backup")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                '<div class="backup-meta-label">Último Backup</div>',
                unsafe_allow_html=True,
            )
            creation = (
                latest_backup.get("creation_date") or latest_backup.get("start_time")
                if latest_backup
                else None
            )
            st.markdown(
                f'<div class="backup-meta-value">{_format_datetime(creation)}</div>',
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown('<div class="backup-meta-label">Estado</div>', unsafe_allow_html=True)
            bk_status = (
                latest_backup.get("status") or latest_backup.get("state") if latest_backup else None
            )
            st.markdown(
                f'<div class="backup-meta-value">{bk_status or "—"}</div>',
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        with st.expander("Ver detalhes", expanded=False):
            if latest_backup:
                st.json(latest_backup)
            error = report.get("error")
            if error:
                st.error(error.get("message", str(error)))


def _render_dynamodb_report(report: dict) -> None:
    resource_arn = report.get("resource_arn", "")
    status = report.get("status", "unknown")
    latest_backup = report.get("latest_backup") or {}
    evidence = report.get("dynamodb_backup_evidence", {}) or {}
    table_description = evidence.get("table_description", {}) or {}
    continuous_backup = evidence.get("continuous_backup_description", {}) or {}
    native_summary = evidence.get("native_backup_summary", {}) or {}

    with st.container(border=True):
        st.markdown(
            f"""
            <div class="resource-group-header">
                <div>
                    <div class="resource-group-title">🧱 DynamoDB</div>
                    <div class="resource-group-subtitle">{resource_arn}</div>
                </div>
                <div>{_status_badge(status)}</div>
            </div>
            <hr class="resource-divider" />
            """,
            unsafe_allow_html=True,
        )

        _render_stale_backup_warning(report, "Último Backup")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(
                '<div class="backup-meta-label">Tabela</div>',
                unsafe_allow_html=True,
            )
            table_name = table_description.get("table_name") or "—"
            st.markdown(
                f'<div class="backup-meta-value">{table_name}</div>',
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                '<div class="backup-meta-label">Último Backup</div>',
                unsafe_allow_html=True,
            )
            backup_time = latest_backup.get("creation_date") or latest_backup.get("start_time")
            st.markdown(
                f'<div class="backup-meta-value">{_format_datetime(backup_time)}</div>',
                unsafe_allow_html=True,
            )
        with col3:
            st.markdown('<div class="backup-meta-label">Estado</div>', unsafe_allow_html=True)
            status_label = latest_backup.get("status") or latest_backup.get("state") or "—"
            st.markdown(
                f'<div class="backup-meta-value">{status_label}</div>',
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        with st.expander("Ver detalhes", expanded=False):
            st.markdown("**Coleta e Estratégia**")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(
                    '<div class="backup-meta-label">Coletado em</div>',
                    unsafe_allow_html=True,
                )
                collected_at_label = _format_datetime(report.get("collected_at"))
                st.markdown(
                    f'<div class="backup-meta-value">{collected_at_label}</div>',
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    '<div class="backup-meta-label">Serviço de Backup</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="backup-meta-value">{report.get("backup_service") or "—"}</div>',
                    unsafe_allow_html=True,
                )
            with c3:
                st.markdown(
                    '<div class="backup-meta-label">Estratégia</div>',
                    unsafe_allow_html=True,
                )
                strategy_label = report.get("collection_strategy") or "—"
                st.markdown(
                    f'<div class="backup-meta-value">{strategy_label}</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("---")
            st.markdown("**Tabela DynamoDB**")
            created_at = _format_datetime(table_description.get("creation_date_time"))
            st.markdown(
                f"- **Nome:** `{table_description.get('table_name') or '—'}`\n"
                f"- **Status da Tabela:** `{table_description.get('table_status') or '—'}`\n"
                f"- **Criada em:** `{created_at}`\n"
                f"- **Itens:** `{table_description.get('item_count') or 0}`\n"
                f"- **Tamanho (bytes):** `{table_description.get('table_size_bytes') or 0}`\n"
                f"- **Modo de cobrança:** `{table_description.get('billing_mode') or '—'}`\n"
                f"- **Criptografia (SSE):** `{table_description.get('sse_status') or '—'}`\n"
                f"- **Tipo SSE:** `{table_description.get('sse_type') or '—'}`"
            )

            st.markdown("---")
            st.markdown("**Backup Contínuo (PITR)**")
            st.markdown(
                f"- **ContinuousBackupsStatus:** `"
                f"{continuous_backup.get('continuous_backups_status') or '—'}`\n"
                f"- **PointInTimeRecoveryStatus:** `"
                f"{continuous_backup.get('point_in_time_recovery_status') or '—'}`\n"
                f"- **EarliestRestorableDateTime:** `"
                f"{_format_datetime(continuous_backup.get('earliest_restorable_datetime'))}`\n"
                f"- **LatestRestorableDateTime:** `"
                f"{_format_datetime(continuous_backup.get('latest_restorable_datetime'))}`"
            )

            st.markdown("---")
            st.markdown("**Último Backup Selecionado**")
            st.markdown(
                f"- **Fonte:** `{latest_backup.get('source') or '—'}`\n"
                f"- **Backup ARN/Recovery Point ARN:** `"
                f"{latest_backup.get('backup_arn_or_recovery_point_arn') or '—'}`\n"
                f"- **Tipo:** `{latest_backup.get('backup_type') or '—'}`\n"
                f"- **Status:** `{latest_backup.get('status') or '—'}`\n"
                f"- **Criado em:** `{_format_datetime(latest_backup.get('creation_date'))}`"
            )

            st.markdown("---")
            st.markdown("**Backups Nativos DynamoDB**")
            st.markdown(
                f"- **Backups encontrados:** `{native_summary.get('backups_found') or 0}`"
            )

            sample_backups = native_summary.get("sample_backups") or []
            if sample_backups:
                import pandas as pd

                rows = []
                for backup in sample_backups:
                    rows.append(
                        {
                            "Nome": backup.get("BackupName") or "—",
                            "Status": backup.get("BackupStatus") or "—",
                            "Tipo": backup.get("BackupType") or "—",
                            "Criado em": _format_datetime(
                                backup.get("BackupCreationDateTime")
                            ),
                            "ARN": backup.get("BackupArn") or "—",
                        }
                    )
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            collection_errors = evidence.get("collection_errors") or []
            if collection_errors:
                st.markdown("---")
                st.markdown("**Erros de Coleta**")
                for error in collection_errors:
                    stage = error.get("stage") or error.get("type") or "coleta"
                    message = error.get("message") or "Erro não identificado."
                    st.error(f"{stage}: {message}")

            if report.get("error"):
                st.markdown("---")
                st.error(report.get("error", {}).get("message", "Erro não identificado."))


def _render_rds_report(report: dict) -> None:
    resource_type = _resource_type_label(report.get("resource_type", ""))
    resource_arn = report.get("resource_arn", "")
    status = report.get("status", "unknown")
    latest_backup = report.get("latest_backup")
    evidence = report.get("rds_snapshot_evidence", {}) or {}
    snapshot_api = evidence.get("snapshot_api", {}) or {}
    resource_status = evidence.get("resource_status", {}) or {}

    with st.container(border=True):
        st.markdown(
            f"""
            <div class="resource-group-header">
                <div>
                    <div class="resource-group-title">🗄️ {resource_type}</div>
                    <div class="resource-group-subtitle">{resource_arn}</div>
                </div>
                <div>{_status_badge(status)}</div>
            </div>
            <hr class="resource-divider" />
            """,
            unsafe_allow_html=True,
        )

        _render_stale_backup_warning(report, "Último Snapshot")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown('<div class="backup-meta-label">Engine</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="backup-meta-value">{resource_status.get("engine") or "—"}</div>',
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                '<div class="backup-meta-label">Último Snapshot</div>',
                unsafe_allow_html=True,
            )
            snapshot_create_time = (
                latest_backup.get("snapshot_create_time") if latest_backup else None
            )
            st.markdown(
                f'<div class="backup-meta-value">{_format_datetime(snapshot_create_time)}</div>',
                unsafe_allow_html=True,
            )
        with col3:
            st.markdown('<div class="backup-meta-label">Estado</div>', unsafe_allow_html=True)
            snapshot_status = latest_backup.get("status") if latest_backup else None
            st.markdown(
                f'<div class="backup-meta-value">{snapshot_status or "—"}</div>',
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        with st.expander("Ver detalhes", expanded=False):
            st.markdown("**Coleta e Estratégia**")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(
                    '<div class="backup-meta-label">Coletado em</div>',
                    unsafe_allow_html=True,
                )
                collected_at_label = _format_datetime(report.get("collected_at"))
                st.markdown(
                    f'<div class="backup-meta-value">{collected_at_label}</div>',
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    '<div class="backup-meta-label">Serviço de Backup</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="backup-meta-value">{report.get("backup_service") or "—"}</div>',
                    unsafe_allow_html=True,
                )
            with c3:
                st.markdown(
                    '<div class="backup-meta-label">Estratégia</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="backup-meta-value">'
                    f'{report.get("collection_strategy") or "—"}</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("---")
            st.markdown("**Recurso RDS**")
            resource_type_label = (
                resource_status.get("resource_type")
                or evidence.get("resource_kind")
                or "—"
            )
            retention_period = resource_status.get("backup_retention_period") or "—"
            backup_window = resource_status.get("preferred_backup_window") or "—"
            latest_restorable = _format_datetime(
                resource_status.get("latest_restorable_time")
            )
            st.markdown(
                f"- **Tipo:** `{resource_type_label}`\n"
                f"- **Identificador:** `{evidence.get('resource_identifier') or '—'}`\n"
                f"- **Engine:** `{resource_status.get('engine') or '—'}`\n"
                f"- **Versão:** `{resource_status.get('engine_version') or '—'}`\n"
                f"- **Retenção de Backup (dias):** `{retention_period}`\n"
                f"- **Janela Preferencial de Backup:** `{backup_window}`\n"
                f"- **Último Ponto Restaurável:** `{latest_restorable}`\n"
                f"- **Criptografado:** "
                f"`{'Sim' if resource_status.get('storage_encrypted') else 'Não'}`"
            )

            st.markdown("---")
            st.markdown("**Snapshots Automatizados**")
            st.markdown(
                f"- **Snapshots encontrados:** `{snapshot_api.get('snapshots_found') or 0}`"
            )

            latest_snapshot = snapshot_api.get("latest_snapshot") or {}
            if latest_snapshot.get("snapshot_identifier"):
                snapshot_created = _format_datetime(
                    latest_snapshot.get("snapshot_create_time")
                )
                st.markdown(
                    f"- **Snapshot mais recente:** `{latest_snapshot.get('snapshot_identifier')}`\n"
                    f"- **Status:** `{latest_snapshot.get('status') or '—'}`\n"
                    f"- **Tipo:** `{latest_snapshot.get('snapshot_type') or '—'}`\n"
                    f"- **Criado em:** `{snapshot_created}`\n"
                    f"- **Engine:** `{latest_snapshot.get('engine') or '—'}`\n"
                    f"- **Versão Engine:** `{latest_snapshot.get('engine_version') or '—'}`\n"
                    f"- **Criptografado:** `{'Sim' if latest_snapshot.get('encrypted') else 'Não'}`"
                )

            sample_snapshots = snapshot_api.get("sample_snapshots") or []
            if sample_snapshots:
                import pandas as pd

                rows = []
                for snapshot in sample_snapshots:
                    identifier = snapshot.get("DBSnapshotIdentifier") or snapshot.get(
                        "DBClusterSnapshotIdentifier"
                    )
                    rows.append(
                        {
                            "Snapshot": identifier or "—",
                            "Status": snapshot.get("Status") or "—",
                            "Tipo": snapshot.get("SnapshotType") or "—",
                            "Criado em": _format_datetime(snapshot.get("SnapshotCreateTime")),
                            "Engine": snapshot.get("Engine") or "—",
                            "Versão": snapshot.get("EngineVersion") or "—",
                        }
                    )

                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            if evidence.get("resource_error"):
                st.markdown("---")
                resource_error_message = evidence.get("resource_error", {}).get(
                    "message", "Erro não identificado."
                )
                st.error(
                    f"Metadados do recurso: {resource_error_message}"
                )

            if snapshot_api.get("error"):
                snapshot_error_message = snapshot_api.get("error", {}).get(
                    "message", "Erro não identificado."
                )
                st.error(
                    f"Snapshots: {snapshot_error_message}"
                )


# ── Layout principal ─────────────────────────────────────────────────────────────

resources = _build_resources()

if not resources:
    st.warning(
        "Nenhum recurso configurado. Defina `OPENSEARCH_RESOURCE_ARN`, "
        "`RDS_ACCOUNT_API_RESOURCE_ARN`, `RDS_CONTENTCORE_API_RESOURCE_ARN` "
        "ou `DYNAMODB_RESOURCE_ARNS` no arquivo `.env`."
    )
    st.stop()

# Botões de ação
col_refresh, col_pdf, _ = st.columns([1, 1, 4])
with col_refresh:
    if st.button("🔄 Atualizar relatório"):
        st.session_state.pop("backup_report_cache", None)

# Coleta com cache na session_state para evitar chamadas repetidas a cada rerun
if "backup_report_cache" not in st.session_state:
    with st.spinner("Coletando evidências de backup..."):
        try:
            st.session_state.backup_report_cache = _collect_report(resources)
            LOGGER.info("backup.report_collected")
        except Exception as exc:
            LOGGER.error("backup.collect_failed error=%s", exc)
            st.error(f"Erro ao coletar evidências de backup: {exc}")
            st.stop()

report_data = st.session_state.backup_report_cache
reports = report_data.get("reports", [])
summary = report_data.get("summary", {})
generated_at = report_data.get("generated_at", "")

# Botão Exportar PDF (disponível assim que o relatório for carregado)
with col_pdf:
    try:
        system_url = os.getenv(
            "STREAMLIT_REDIRECT_URL", "http://localhost:8501"
        )
        pdf_bytes = generate_pdf(report_data, system_url=system_url)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        st.download_button(
            label="📄 Exportar PDF",
            data=pdf_bytes,
            file_name=f"evidencias_backup_{ts}.pdf",
            mime="application/pdf",
        )
    except Exception as exc:
        LOGGER.error("backup.pdf_generation_failed error=%s", exc)
        st.error(f"Erro ao gerar PDF: {exc}")

# Resumo global
st.markdown(f"*Relatório gerado em: {_format_datetime(generated_at)}*")
st.markdown("<br>", unsafe_allow_html=True)

reports_with_partial = sum(1 for item in reports if _is_effective_partial(item))
reports_unsupported = sum(
    1
    for item in reports
    if item.get("status") == "resource_not_supported_by_aws_backup"
)

mcol1, mcol2, mcol3, mcol4, mcol5 = st.columns(5)
mcol1.metric("Total de Recursos", summary.get("total_resources", 0))
mcol2.metric("Com Backup", summary.get("resources_with_backup", 0))
mcol3.metric("Sem Backup", summary.get("resources_without_backup", 0))
mcol4.metric("Com Erro", summary.get("resources_with_error", 0))
mcol5.metric("Parciais", reports_with_partial)

if reports_unsupported > 0:
    st.info(
        "Alguns recursos não são suportados pelo AWS Backup para este tipo de consulta: "
        f"{reports_unsupported}."
    )

if summary.get("resources_with_error", 0) > 0:
    st.warning(
        "Foram identificados recursos com erro de coleta. "
        "Eles aparecem no topo para facilitar diagnóstico."
    )

status_overview = _build_status_overview(reports)
if status_overview:
    st.markdown(status_overview, unsafe_allow_html=True)

st.markdown("---")

# Relatório por recurso
ordered_reports = sorted(
    reports,
    key=lambda item: (
        _status_priority(str(item.get("status") or "unknown")),
        str(item.get("resource_type") or ""),
        str(item.get("resource_arn") or ""),
    ),
)

for index, report in enumerate(ordered_reports, start=1):
    resource_type = (report.get("resource_type") or "").lower()

    st.markdown(
        f'<div class="backup-section-title">Recurso {index}</div>',
        unsafe_allow_html=True,
    )

    if resource_type == "opensearch":
        _render_opensearch_report(report)
    elif resource_type in {"rds", "rds_instance", "rds_cluster"}:
        _render_rds_report(report)
    elif resource_type == "dynamodb":
        _render_dynamodb_report(report)
    else:
        _render_generic_report(report)

st.markdown("---")
st.markdown(
    f"""
    <div style='text-align: center; color: #64748b; font-size: 12px;'>
        <p>© {datetime.now().year} Midiacode Ops Manager</p>
        <p>Versão {APP_VERSION}</p>
    </div>
    """,
    unsafe_allow_html=True,
)
