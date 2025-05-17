import streamlit as st
import pandas as pd
import requests
from requests.exceptions import RequestException
from datetime import datetime
import time
import json
import os

# Configuração da página (deve ser a primeira chamada do Streamlit)
st.set_page_config(
    page_title="Status Midiacode",
    page_icon="⚙️",
    layout="wide"
)

# Estilos CSS para elementos específicos (mais minimalista)
st.markdown("""
<style>
    .google-header-title {
        font-size: 24px;
        font-weight: 500; /* Google Sans often uses medium weight */
        color: #202124; /* Dark grey, common in Google UIs */
        display: flex;
        align-items: center;
        margin-bottom: 4px;
    }
    .google-header-logo {
        font-size: 28px; /* Slightly larger for the icon */
        margin-right: 10px;
    }
    .google-header-subtitle {
        font-size: 14px;
        color: #5f6368; /* Lighter grey for subtitles */
        margin-bottom: 24px;
    }
    .status-operational {
        color: #137333; /* Google's green for operational */
        font-weight: 500;
    }
    .status-disruption {
        color: #c5221f; /* Google's red for disruption */
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
    .details-button {
        /* Estilo para o botão de detalhes, se necessário, mas st.button é preferível */
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
</style>
""", unsafe_allow_html=True)

# Cabeçalho
st.markdown('<div class="google-header-title"><span class="google-header-logo">⚙️</span>Midiacode Status Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="google-header-subtitle">Este painel fornece informações de status sobre os serviços do ambiente Midiacode.<br>Verifique aqui para ver o status atual dos serviços listados abaixo.</div>', unsafe_allow_html=True)


# Sidebar para navegação
with st.sidebar:
    st.title("Navegação")
    option = st.selectbox(
        "Selecione uma opção",
        ["Dashboard", "Relatórios", "Configurações"]
    )
    
    st.write("Usuário: Admin")
    
    # Adicionar tempo da última verificação
    if 'last_check_time' not in st.session_state:
        st.session_state.last_check_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    st.write(f"Última verificação: {st.session_state.last_check_time}")

# Função para verificar o status de um sistema
def check_system_status(url):
    try:
        start_time = time.time()
        response = requests.get(url, timeout=10) # Aumentado timeout para 10s
        response_time = time.time() - start_time
        return response.status_code == 200, round(response_time * 1000)  # Tempo em ms
    except RequestException:
        return False, None
        
# Função para salvar o histórico de status
def save_status_history(system_name, status, timestamp):
    history_file = "system_status_history.json"
    
    # Inicializar ou carregar o histórico existente
    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            try:
                history = json.load(f)
            except json.JSONDecodeError:
                history = {}
    else:
        history = {}
    
    # Inicializar o sistema se não existir no histórico
    if system_name not in history:
        history[system_name] = []
    
    # Limitar o histórico a 100 entradas por sistema
    if len(history[system_name]) >= 100:
        history[system_name].pop(0)
    
    # Adicionar o novo status
    history[system_name].append({
        "timestamp": timestamp,
        "status": status
    })
    
    # Salvar o histórico atualizado
    with open(history_file, "w") as f:
        json.dump(history, f)

# Conteúdo principal baseado na opção selecionada
if option == "Dashboard":
    # Inicializar o estado da sessão para o status dos sistemas
    if 'system_status' not in st.session_state:
        st.session_state.system_status = {}
    if 'last_refresh_time' not in st.session_state:
        st.session_state.last_refresh_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    if 'selected_system_details' not in st.session_state:
        st.session_state.selected_system_details = None


    sistemas = {
        "Content Spot API": "https://dev.contentspot.midiacode.pt/health",
        "Account API": "https://dev.account.midiacode.pt/ht/", # URL de exemplo, pode precisar de ajuste
        "Content Core API": "https://dev.contentcore.midiacode.pt/admin/login/" # URL de exemplo
    }

    current_time_dt = datetime.now()
    formatted_current_time = current_time_dt.strftime("%d/%m/%Y %H:%M:%S")

    # Linha de atualização
    col1, col2 = st.columns([3,1])
    with col1:
        st.caption(f"Última atualização: {st.session_state.last_refresh_time}")
    with col2:
        if st.button("🔄 Atualizar Agora"):
            st.session_state.last_refresh_time = formatted_current_time
            # Forçar a re-verificação de todos os sistemas
            for nome in sistemas.keys():
                if nome in st.session_state.system_status: # Evitar erro se o estado ainda não foi inicializado
                    st.session_state.system_status[nome]['force_refresh'] = True
            st.rerun()


    # Legenda dos status
    st.markdown("""
    <div style="margin-bottom: 16px; display: flex; align-items: center; gap: 20px;">
        <div style="display: flex; align-items: center;"><span class="status-indicator-dot operational-dot"></span><span>Operacional</span></div>
        <div style="display: flex; align-items: center;"><span class="status-indicator-dot disruption-dot"></span><span>Indisponível</span></div>
    </div>
    """, unsafe_allow_html=True)

    # Cabeçalhos da "tabela"
    cols = st.columns([3, 2, 2, 1.5]) # Ajuste as proporções conforme necessário
    cols[0].markdown("**Serviço**")
    cols[1].markdown("**Status Atual**")
    cols[2].markdown("**Tempo de Resposta**")
    cols[3].markdown("**Detalhes**")
    # st.markdown("---") # Linha divisória removida para reduzir o espaçamento

    for nome, url in sistemas.items():
        # Verificar e atualizar o status se necessário
        force_refresh = st.session_state.system_status.get(nome, {}).get('force_refresh', False)
        if force_refresh or nome not in st.session_state.system_status:
            status, response_time = check_system_status(url)
            st.session_state.system_status[nome] = {
                "status": status,
                "last_check": formatted_current_time, # Usar o tempo da atualização atual
                "response_time": response_time,
                "force_refresh": False # Resetar o flag
            }
            save_status_history(nome, status, formatted_current_time)
        
        current_status_info = st.session_state.system_status[nome]
        status = current_status_info["status"]
        response_time = current_status_info["response_time"]

        status_text = "Operacional" if status else "Indisponível"
        status_class = "status-operational" if status else "status-disruption"
        status_dot_class = "operational-dot" if status else "disruption-dot"
        
        tempo_resposta_text = f"{response_time} ms" if response_time is not None else "N/A"

        row_cols = st.columns([3, 2, 2, 1.5])
        row_cols[0].markdown(f"**{nome}**")
        row_cols[1].markdown(f'<span class="status-indicator-dot {status_dot_class}"></span><span class="{status_class}">{status_text}</span>', unsafe_allow_html=True)
        row_cols[2].markdown(tempo_resposta_text)
        
        if row_cols[3].button("Ver Detalhes", key=f"details_{nome.replace(' ', '_')}", use_container_width=True):
            st.session_state.selected_system_details = nome
            st.rerun() # Rerun para mostrar/atualizar o expander
        # st.markdown("---") # Linha divisória entre os serviços removida para diminuir o espaçamento

    # Seção de Detalhes (usando st.expander ou uma área dedicada)
    if st.session_state.selected_system_details:
        selected_system_name = st.session_state.selected_system_details
        system_info = st.session_state.system_status.get(selected_system_name)
        
        if system_info:
            status_text = "Operacional" if system_info["status"] else "Indisponível"
            status_class = "status-operational" if system_info["status"] else "status-disruption"
            status_dot_class = "operational-dot" if system_info["status"] else "disruption-dot"
            url_sistema = sistemas.get(selected_system_name, "URL não encontrada")
            
            with st.expander(f"Detalhes de {selected_system_name}", expanded=True):
                st.markdown(f"**Serviço:** {selected_system_name}")
                st.markdown(f"**Status Atual:** <span class='status-indicator-dot {status_dot_class}'></span><span class='{status_class}'>{status_text}</span>", unsafe_allow_html=True)
                st.markdown(f"**URL do Serviço:** [{url_sistema}]({url_sistema})")
                st.markdown(f"**Última Verificação:** {system_info['last_check']}")
                st.markdown(f"**Tempo de Resposta:** {system_info['response_time'] or 'N/A'} ms")
                
                # Carregar e exibir histórico (simplificado)
                history_file = "system_status_history.json"
                if os.path.exists(history_file):
                    with open(history_file, "r") as f:
                        try:
                            full_history = json.load(f)
                            system_history = full_history.get(selected_system_name, [])
                            if system_history:
                                st.markdown("**Histórico Recente:**")
                                # Mostrar as últimas 5 entradas, por exemplo
                                for entry in reversed(system_history[-5:]):
                                    history_status_text = "Operacional" if entry['status'] else "Indisponível"
                                    st.caption(f"- {entry['timestamp']}: {history_status_text}")
                            else:
                                st.caption("Nenhum histórico disponível para este serviço.")
                        except json.JSONDecodeError:
                            st.caption("Erro ao carregar o histórico.")
                else:
                    st.caption("Arquivo de histórico não encontrado.")

                st.markdown("""
                <div style="margin-top:20px;padding-top:16px;border-top:1px solid #dadce0;color:#5f6368;font-size:13px;">
                    Caso encontre problemas, entre em contato com a equipe de operações em 
                    <a href="mailto:suporte@midiacode.pt" style="color:#1a73e8;text-decoration:none;">suporte@midiacode.pt</a>.
                </div>
                """, unsafe_allow_html=True)
                if st.button("Fechar Detalhes", key=f"close_details_{selected_system_name.replace(' ', '_')}"):
                    st.session_state.selected_system_details = None
                    st.rerun()

elif option == "Relatórios":
    st.header("Relatórios")
    st.write("Esta seção está em desenvolvimento.")
    
    report_type = st.selectbox(
        "Tipo de Relatório",
        ["Diário", "Semanal", "Mensal"]
    )
    
    if st.button("Gerar Relatório"):
        with st.spinner("Gerando relatório..."):
            st.success(f"Relatório {report_type} gerado com sucesso!")

elif option == "Configurações":
    st.header("Configurações")
    
    with st.form("config_form"):
        st.write("Configurações do Sistema")
        
        name = st.text_input("Nome da Empresa")
        email = st.text_input("Email para Contato")
        notification = st.checkbox("Ativar notificações")
        
        submitted = st.form_submit_button("Salvar Configurações")
        if submitted:
            st.success("Configurações salvas com sucesso!")

# Rodapé
st.markdown("""
<div class="footer">
    <div>© """ + str(datetime.now().year) + """ Midiacode Status Dashboard</div>
    <div class="footer-links">
        <a href="#">Documentação</a>
        <a href="#">Feed RSS</a>
        <a href="#">API</a>
        <a href="#">Enviar feedback</a>
        <a href="#">Política de privacidade</a>
    </div>
</div>
""", unsafe_allow_html=True)
