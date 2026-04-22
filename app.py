import streamlit as st
import requests
from requests.exceptions import RequestException
from datetime import datetime
import time
import os
import logging
import boto3
from dotenv import load_dotenv
from uuid import uuid4

from slack_notifications import send_slack_deploy_notification
from auth import display_auth_ui


LOGGER = logging.getLogger("ops_manager.app")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    LOGGER.addHandler(_handler)
LOGGER.setLevel(os.getenv("APP_LOG_LEVEL", os.getenv("AUTH_LOG_LEVEL", "INFO")).upper())
LOGGER.propagate = False


def _get_trace_id() -> str:
    if "auth_trace_id" not in st.session_state:
        st.session_state.auth_trace_id = uuid4().hex[:12]
    return st.session_state.auth_trace_id


def _log_app(level: int, event: str, **fields):
    payload = {
        "event": event,
        "trace_id": _get_trace_id(),
    }
    payload.update(fields)
    LOGGER.log(level, " ".join(f"{k}={v}" for k, v in payload.items()))


# Configuração da página (deve ser a primeira chamada do Streamlit)
st.set_page_config(
    page_title="Midiacode Ops Manager",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)
_log_app(logging.INFO, "app.page_configured")

# Verificar autenticação - deve ser chamado antes de qualquer conteúdo
display_auth_ui()
_log_app(logging.INFO, "app.auth_ok")

# Estilos CSS para elementos específicos (mais minimalista)
st.markdown("""
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

    @media (max-width: 900px) {
        .ops-page-header {
            flex-direction: column;
            align-items: flex-start;
        }

        .ops-page-title {
            font-size: 25px;
        }
    }

    .google-header-title {
        font-size: 24px;
        font-weight: 500;
        color: #202124;
        margin-bottom: 4px;
    }
    .google-header-brand {
        font-size: 12px;
        color: #5f6368;
        margin-bottom: 16px;
    }
    .google-header-subtitle {
        font-size: 14px;
        color: #5f6368;
        margin-bottom: 24px;
    }
    .status-operational {
        color: #137333;
        font-weight: 500;
    }
    .status-disruption {
        color: #c5221f;
        font-weight: 500;
    }
    .status-indicator-dot {
        display: inline-block;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        margin-right: 8px;
    }
    .operational-dot {
        background-color: #137333;
    }
    .disruption-dot {
        background-color: #c5221f;
    }
    .footer {
        font-size: 12px;
        color: #5f6368;
        text-align: center;
        padding-top: 30px;
        border-top: 1px solid #dadce0;
        margin-top: 30px;
    }
    .footer-links a {
        color: #5f6368;
        text-decoration: none;
        margin: 0 5px;
    }
    .footer-links a:hover {
        text-decoration: underline;
    }
    <style>
    div.stButton > button {
        background-color: #0067ff;
        color: white;
    }
    </style>
</style>
""", unsafe_allow_html=True)

# Cabeçalho
st.markdown(
    """
    <div class="ops-page-header">
        <div>
            <h1 class="ops-page-title">Painel</h1>
            <div class="ops-page-subtitle">
                Este painel fornece informações de status sobre os serviços do
                ambiente de sandbox do Midiacode. Verifique aqui o status atual
                dos serviços listados abaixo.
            </div>
        </div>
        <div class="ops-page-badge">Sandbox</div>
    </div>
    """,
    unsafe_allow_html=True,
)


def check_system_status(url):
    try:
        start_time = time.time()
        response = requests.get(url, timeout=10)
        response_time = time.time() - start_time
        is_ok = response.status_code == 200
        elapsed_ms = round(response_time * 1000)
        _log_app(
            logging.DEBUG,
            "system_status.checked",
            url=url,
            status_code=response.status_code,
            ok=is_ok,
            response_ms=elapsed_ms,
        )
        return is_ok, elapsed_ms
    except RequestException:
        _log_app(logging.WARNING, "system_status.error", url=url)
        return False, None


load_dotenv()
_log_app(logging.DEBUG, "app.env_loaded")

# Funções para ligar/desligar ambiente de dev


def start_dev_environment():
    _log_app(logging.INFO, "dev_env.start.requested")
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    response = lambda_client.invoke(
        FunctionName='arn:aws:lambda:us-east-1:578416043364:function:aws-operations-tools-prod-lambda_handler_start_dev_environment',
        InvocationType='RequestResponse'
    )
    status_code = response['StatusCode']
    payload = response['Payload'].read().decode() if 'Payload' in response else ''
    _log_app(logging.INFO, "dev_env.start.completed", status_code=status_code)
    return status_code, payload


def stop_dev_environment():
    _log_app(logging.INFO, "dev_env.stop.requested")
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    response = lambda_client.invoke(
        FunctionName='arn:aws:lambda:us-east-1:578416043364:function:aws-operations-tools-prod-lambda_handler_stop_dev_environment',
        InvocationType='RequestResponse'
    )
    status_code = response['StatusCode']
    payload = response['Payload'].read().decode() if 'Payload' in response else ''
    _log_app(logging.INFO, "dev_env.stop.completed", status_code=status_code)
    return status_code, payload


# Conteúdo principal - Dashboard
if 'system_status' not in st.session_state:
    st.session_state.system_status = {}
if 'last_refresh_time' not in st.session_state:
    st.session_state.last_refresh_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
if 'selected_system_details' not in st.session_state:
    st.session_state.selected_system_details = None
_log_app(logging.DEBUG, "app.session_state_ready")

sistemas = {
    "Content Spot API": "https://dev.contentspot.midiacode.pt/health",
    "Account API": "https://dev.account.midiacode.pt/ht/",
    "Content Core API": "https://dev.contentcore.midiacode.pt/hc/",
    "Midiacode Studio": "https://dev.studio.midiacode.pt/",
    "Point System Mini-App": "https://dev.point-system.midiacode.pt/",
    "Midiacode Lite": "https://sandbox.1mc.co/health"
}

current_time_dt = datetime.now()
formatted_current_time = current_time_dt.strftime("%d/%m/%Y %H:%M:%S")

# Verifica se todos os sistemas estão operacionais
all_systems_operational = all(
    check_system_status(url)[0] for url in sistemas.values()
)
_log_app(
    logging.INFO,
    "systems.aggregate_status",
    all_operational=all_systems_operational,
    total_systems=len(sistemas),
)

ligado = st.toggle(
    "Ligado",
    value=all_systems_operational,
    key="toggle_env_btn",
    help="Ligar ou desligar ambiente de desenvolvimento"
)

if 'last_toggle_state' not in st.session_state:
    st.session_state.last_toggle_state = all_systems_operational

if ligado != st.session_state.last_toggle_state:
    _log_app(
        logging.INFO,
        "toggle.changed",
        new_state=ligado,
        previous_state=st.session_state.last_toggle_state,
    )
    if ligado:
        with st.spinner("Ligando ambiente de desenvolvimento..."):
            status_code, payload = start_dev_environment()
            if status_code == 200:
                st.success("A solicitação de ligamento do ambiente de desenvolvimento foi recebida com sucesso! Aguarde alguns minutos para ficar totalmente disponível.")
            else:
                st.error(f"Erro ao ligar ambiente: {payload}")

            slack_sent, slack_error = send_slack_deploy_notification(
                action="iniciando",
                source="streamlit",
                status_code=status_code,
                payload=payload,
            )
            _log_app(
                logging.INFO,
                "slack.notification.sent",
                action="iniciando",
                sent=slack_sent,
                has_error=bool(slack_error),
            )
            if not slack_sent and os.getenv("SLACK_DEPLOY_WEBHOOK_URL"):
                st.warning(f"Falha ao enviar notificacao para o Slack: {slack_error}")
    else:
        with st.spinner("Desligando ambiente de desenvolvimento..."):
            status_code, payload = stop_dev_environment()
            if status_code == 200:
                st.success("A solicitação de desligamento do ambiente de desenvolvimento foi recebida com sucesso! Aguarde alguns minutos para o ambiente ser totalmente desligado.")
            else:
                st.error(f"Erro ao desligar ambiente: {payload}")

            slack_sent, slack_error = send_slack_deploy_notification(
                action="desligando",
                source="streamlit",
                status_code=status_code,
                payload=payload,
            )
            _log_app(
                logging.INFO,
                "slack.notification.sent",
                action="desligando",
                sent=slack_sent,
                has_error=bool(slack_error),
            )
            if not slack_sent and os.getenv("SLACK_DEPLOY_WEBHOOK_URL"):
                st.warning(f"Falha ao enviar notificacao para o Slack: {slack_error}")
    st.session_state.last_toggle_state = ligado

refresh_clicked = st.button(
    label="\U0001F504 Atualizar Status",  # Unicode refresh icon
    key="refresh_btn",
    help="Atualizar status dos sistemas",   
    type="primary",  
)

if refresh_clicked:
    _log_app(logging.INFO, "systems.refresh.clicked")
    st.session_state.last_refresh_time = formatted_current_time
    for nome in sistemas.keys():
        if nome in st.session_state.system_status:
            st.session_state.system_status[nome]['force_refresh'] = True
    st.rerun()

st.markdown("""
<div style="margin-bottom: 16px; display: flex; align-items: center; gap: 20px;">
    <div style="display: flex; align-items: center;"><span class="status-indicator-dot operational-dot"></span><span>Operacional</span></div>
    <div style="display: flex; align-items: center;"><span class="status-indicator-dot disruption-dot"></span><span>Indisponível</span></div>
</div>
""", unsafe_allow_html=True)

cols = st.columns([3, 2, 2])
cols[0].markdown("**Serviço**")
cols[1].markdown("**Status Atual**")
cols[2].markdown("**Tempo de Resposta**")

for nome, url in sistemas.items():
    force_refresh = st.session_state.system_status.get(nome, {}).get('force_refresh', False)
    if force_refresh or nome not in st.session_state.system_status:
        status, response_time = check_system_status(url)
        st.session_state.system_status[nome] = {
            "status": status,
            "last_check": formatted_current_time,
            "response_time": response_time,
            "force_refresh": False
        }
    current_status_info = st.session_state.system_status[nome]
    status = current_status_info["status"]
    response_time = current_status_info["response_time"]
    status_text = "Operacional" if status else "Indisponível"
    status_class = "status-operational" if status else "status-disruption"
    status_dot_class = "operational-dot" if status else "disruption-dot"
    tempo_resposta_text = f"{response_time} ms" if response_time is not None else "N/A"
    row_cols = st.columns([3, 2, 2])
    row_cols[0].markdown(f"**{nome}**")
    row_cols[1].markdown(f'<span class="status-indicator-dot {status_dot_class}"></span><span class="{status_class}">{status_text}</span>', unsafe_allow_html=True)
    row_cols[2].markdown(tempo_resposta_text)
    _log_app(
        logging.DEBUG,
        "systems.row_rendered",
        system=nome,
        status=status_text,
        response_ms=response_time,
    )

st.caption(f"Última atualização: {st.session_state.last_refresh_time}")

# Rodapé
st.markdown("""
<div class="footer">
    <div>© """ + str(datetime.now().year) + """ Midiacode Ops Manager</div>
</div>
""", unsafe_allow_html=True)
