import streamlit as st
import requests
from requests.exceptions import RequestException
from datetime import datetime
import time
import json
import os
import boto3
from dotenv import load_dotenv

# Configuração da página (deve ser a primeira chamada do Streamlit)
st.set_page_config(
    page_title="Midiacode Ops Manager",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="collapsed"
)
st.logo("icone_midiacode.png", link="https://midiacode.com/")
# Estilos CSS para elementos específicos (mais minimalista)
st.markdown("""
<style>
    .google-header-title {
        font-size: 24px;
        font-weight: 500;
        color: #202124;
        display: flex;
        align-items: center;
        margin-bottom: 4px;
    }
    .google-header-logo {
        font-size: 28px;
        margin-right: 10px;
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
st.markdown('<div class="google-header-title"><span class="google-header-logo">⚙️</span>Midiacode Ops Manager</div>', unsafe_allow_html=True)
st.markdown('<div class="google-header-subtitle">Este painel fornece informações de status sobre os serviços do ambiente de desenvolvimento do Midiacode.<br>Verifique aqui para ver o status atual dos serviços listados abaixo.</div>', unsafe_allow_html=True)

# Sidebar para navegação
with st.sidebar:
    st.title("Menu")
    option = st.selectbox(
        "Selecione uma opção",
        ["Dashboard"]
    )
    # st.write("Usuário: Admin")
    if 'last_check_time' not in st.session_state:
        st.session_state.last_check_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    # st.write(f"Última verificação: {st.session_state.last_check_time}")

# Função para verificar o status de um sistema
def check_system_status(url):
    try:
        start_time = time.time()
        response = requests.get(url, timeout=10)
        response_time = time.time() - start_time
        return response.status_code == 200, round(response_time * 1000)
    except RequestException:
        return False, None


load_dotenv()

# Funções para ligar/desligar ambiente de dev

def start_dev_environment():
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    response = lambda_client.invoke(
        FunctionName='arn:aws:lambda:us-east-1:578416043364:function:aws-operations-tools-prod-lambda_handler_start_dev_environment',
        InvocationType='RequestResponse'
    )
    status_code = response['StatusCode']
    payload = response['Payload'].read().decode() if 'Payload' in response else ''
    return status_code, payload

def stop_dev_environment():
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    response = lambda_client.invoke(
        FunctionName='arn:aws:lambda:us-east-1:578416043364:function:aws-operations-tools-prod-lambda_handler_stop_dev_environment',
        InvocationType='RequestResponse'
    )
    status_code = response['StatusCode']
    payload = response['Payload'].read().decode() if 'Payload' in response else ''
    return status_code, payload

# Conteúdo principal baseado na opção selecionada
if option == "Dashboard":
    if 'system_status' not in st.session_state:
        st.session_state.system_status = {}
    if 'last_refresh_time' not in st.session_state:
        st.session_state.last_refresh_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    if 'selected_system_details' not in st.session_state:
        st.session_state.selected_system_details = None

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

    ligado = st.toggle(
        "Ligado",
        value=all_systems_operational,
        key="toggle_env_btn",
        help="Ligar ou desligar ambiente de desenvolvimento"
    )

    if 'last_toggle_state' not in st.session_state:
        st.session_state.last_toggle_state = all_systems_operational

    if ligado != st.session_state.last_toggle_state:
        if ligado:
            with st.spinner("Ligando ambiente de desenvolvimento..."):
                status_code, payload = start_dev_environment()
                if status_code == 200:
                    st.success("A solicitação de ligamento do ambiente de desenvolvimento foi recebida com sucesso! Aguarde alguns minutos para ficar totalmente disponível.")
                else:
                    st.error(f"Erro ao ligar ambiente: {payload}")
        else:
            with st.spinner("Desligando ambiente de desenvolvimento..."):
                status_code, payload = stop_dev_environment()
                if status_code == 200:
                    st.success("A solicitação de desligamento do ambiente de desenvolvimento foi recebida com sucesso! Aguarde alguns minutos para o ambiente ser totalmente desligado.")
                else:
                    st.error(f"Erro ao desligar ambiente: {payload}")
        st.session_state.last_toggle_state = ligado

    refresh_clicked = st.button(
        label="\U0001F504 Atualizar Status",  # Unicode refresh icon
        key="refresh_btn",
        help="Atualizar status dos sistemas",   
        type="primary",  
    )

    if refresh_clicked:
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

    st.caption(f"Última atualização: {st.session_state.last_refresh_time}")

# Rodapé
st.markdown("""
<div class="footer">
    <div>© """ + str(datetime.now().year) + """ Midiacode Ops Manager</div>
</div>
""", unsafe_allow_html=True)
