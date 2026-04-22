"""
Página de Evidências de Backup
Exibe o relatório dos últimos backups dos recursos AWS monitorados.
"""

import logging
import os

import streamlit as st
from dotenv import load_dotenv

from auth import display_auth_ui
from backup_evidence_report import AwsBackupEvidenceCollector, BackupResource
from backup_pdf_report import generate_pdf

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
        padding: 16px 20px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        background: #ffffff;
        margin-bottom: 12px;
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
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Cabeçalho ────────────────────────────────────────────────────────────────────

st.markdown(
    """
    <div class="ops-page-header">
        <div>
            <h1 class="ops-page-title">Evidências de Backup</h1>
            <div class="ops-page-subtitle">
                Relatório dos últimos backups e snapshots dos recursos AWS monitorados.
                Os dados são coletados em tempo real via AWS CLI e API de snapshots.
            </div>
        </div>
        <div class="ops-page-badge">Backup</div>
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


def _format_datetime(raw: str | None) -> str:
    if not raw:
        return "—"
    try:
        normalized = raw.replace("Z", "+00:00")
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(normalized).astimezone(timezone.utc)
        return dt.strftime("%d/%m/%Y %H:%M UTC")
    except Exception:
        return raw


def _resource_type_label(resource_type: str) -> str:
    labels = {
        "opensearch": "OpenSearch",
        "rds": "RDS",
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

    # Resumo do card
    st.markdown(
        f"""
        <div class="backup-card">
            <div class="backup-card-title">
                🔍 OpenSearch — {domain_status.get("domain_name") or "search-service"}
            </div>
            <div class="backup-card-arn">{resource_arn}</div>
            {_status_badge(status)}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Métricas rápidas
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown('<div class="backup-meta-label">Motor</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="backup-meta-value">{domain_status.get("engine_version") or "—"}</div>',
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown('<div class="backup-meta-label">Último Snapshot</div>', unsafe_allow_html=True)
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

    with st.expander("Ver detalhes"):
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

    st.markdown(
        f"""
        <div class="backup-card">
            <div class="backup-card-title">📦 {resource_type}</div>
            <div class="backup-card-arn">{resource_arn}</div>
            {_status_badge(status)}
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="backup-meta-label">Último Backup</div>', unsafe_allow_html=True)
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

    with st.expander("Ver detalhes"):
        if latest_backup:
            st.json(latest_backup)
        error = report.get("error")
        if error:
            st.error(error.get("message", str(error)))


# ── Layout principal ─────────────────────────────────────────────────────────────

resources = _build_resources()

if not resources:
    st.warning(
        "Nenhum recurso configurado. Defina `OPENSEARCH_RESOURCE_ARN` no arquivo `.env`."
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
        from datetime import datetime, timezone
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

mcol1, mcol2, mcol3, mcol4 = st.columns(4)
mcol1.metric("Total de Recursos", summary.get("total_resources", 0))
mcol2.metric("Com Backup", summary.get("resources_with_backup", 0))
mcol3.metric("Sem Backup", summary.get("resources_without_backup", 0))
mcol4.metric("Com Erro", summary.get("resources_with_error", 0))

st.markdown("---")

# Relatório por recurso
for report in reports:
    resource_type = (report.get("resource_type") or "").lower()

    if resource_type == "opensearch":
        _render_opensearch_report(report)
    else:
        _render_generic_report(report)
