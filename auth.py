"""
Módulo de autenticação com Supabase e Google Login
"""

import streamlit as st
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
import base64
import os
from typing import Optional, Dict, Any
from datetime import datetime
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

# Carregar variáveis de ambiente
load_dotenv()

# Configurações do Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
REDIRECT_URL = os.getenv("STREAMLIT_REDIRECT_URL", "http://localhost:8501")
ICON_PATH = os.path.join(os.path.dirname(__file__), "icone_midiacode.png")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL e SUPABASE_KEY não configurados no .env")


def get_supabase_client() -> Client:
    """Retorna uma instância do cliente Supabase"""
    return create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=ClientOptions(storage=StreamlitSessionStorage()),
    )


class StreamlitSessionStorage:
    """Storage síncrono do Supabase Auth persistido no st.session_state."""

    STORAGE_KEY = "_supabase_auth_storage"

    def _get_storage(self) -> Dict[str, str]:
        if self.STORAGE_KEY not in st.session_state:
            st.session_state[self.STORAGE_KEY] = {}
        return st.session_state[self.STORAGE_KEY]

    def get_item(self, key: str) -> Optional[str]:
        return self._get_storage().get(key)

    def set_item(self, key: str, value: str) -> None:
        self._get_storage()[key] = value

    def remove_item(self, key: str) -> None:
        self._get_storage().pop(key, None)


def initialize_auth_session():
    """Inicializa as variáveis de sessão necessárias para autenticação"""
    if "session" not in st.session_state:
        st.session_state.session = None
    if "user" not in st.session_state:
        st.session_state.user = None
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "_supabase_auth_storage" not in st.session_state:
        st.session_state._supabase_auth_storage = {}


def get_google_oauth_url() -> str:
    """Gera a URL de login do Google através do Supabase"""
    try:
        client = get_supabase_client()
        redirect_to = REDIRECT_URL
        response = client.auth.sign_in_with_oauth(
            {
                "provider": "google",
                "options": {
                    "redirect_to": redirect_to,
                    "scopes": "profile email",
                },
            }
        )
        code_verifier = client.auth._storage.get_item(
            f"{client.auth._storage_key}-code-verifier"
        )
        if response and response.url and code_verifier:
            return append_query_params(
                response.url,
                {
                    "redirect_to": append_query_params(
                        redirect_to,
                        {"pkce_code_verifier": code_verifier},
                    )
                },
            )
        return response.url if response else None
    except Exception as e:
        st.error(f"Erro ao gerar URL de login: {str(e)}")
        return None


def append_query_params(url: str, extra_params: Dict[str, str]) -> str:
    """Retorna uma URL com parâmetros de query adicionados/substituídos."""
    parsed_url = urlparse(url)
    query_params = dict(parse_qsl(parsed_url.query, keep_blank_values=True))
    query_params.update(extra_params)
    return urlunparse(
        parsed_url._replace(query=urlencode(query_params))
    )


def get_login_logo_src() -> Optional[str]:
    """Retorna o icone local da Midiacode como data URI para uso no HTML do login."""
    try:
        with open(ICON_PATH, "rb") as image_file:
            encoded_icon = base64.b64encode(image_file.read()).decode("utf-8")
        return f"data:image/png;base64,{encoded_icon}"
    except OSError:
        return None


def get_google_icon_src() -> str:
    """Retorna o ícone oficial do Google como data URI para uso no botão de login."""
    google_svg = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
        <path fill="#4285F4" d="M23.49 12.27c0-.79-.07-1.55-.2-2.27H12v4.3h6.45a5.52 5.52 0 0 1-2.4 3.62v3h3.88c2.27-2.09 3.56-5.18 3.56-8.65Z"/>
        <path fill="#34A853" d="M12 24c3.24 0 5.96-1.07 7.95-2.91l-3.88-3c-1.08.72-2.46 1.14-4.07 1.14-3.13 0-5.78-2.11-6.73-4.96H1.26v3.09A11.99 11.99 0 0 0 12 24Z"/>
        <path fill="#FBBC05" d="M5.27 14.27A7.2 7.2 0 0 1 4.91 12c0-.79.14-1.56.36-2.27V6.64H1.26A11.99 11.99 0 0 0 0 12c0 1.93.46 3.76 1.26 5.36l4.01-3.09Z"/>
        <path fill="#EA4335" d="M12 4.77c1.76 0 3.34.61 4.58 1.8l3.43-3.43C17.95 1.18 15.24 0 12 0A11.99 11.99 0 0 0 1.26 6.64l4.01 3.09c.95-2.85 3.6-4.96 6.73-4.96Z"/>
    </svg>
    """.strip()
    encoded_icon = base64.b64encode(google_svg.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{encoded_icon}"


def handle_auth_callback():
    """
    Processa o callback da autenticação do Google
    Deve ser chamado na URL com parâmetro code
    """
    query_params = st.query_params
    
    if "code" in query_params:
        try:
            client = get_supabase_client()
            code = query_params["code"]
            code_verifier = query_params.get("pkce_code_verifier")
            
            # Troca o código por uma sessão
            response = client.auth.exchange_code_for_session(
                {
                    "auth_code": code,
                    "code_verifier": code_verifier,
                }
            )
            
            if response:
                st.session_state.session = response.session
                st.session_state.user = response.user
                st.session_state.authenticated = True
                
                # Limpar parâmetros de query
                st.query_params.clear()
                st.rerun()
                
        except Exception as e:
            st.error(f"Erro ao processar autenticação: {str(e)}")


def check_session():
    """
    Verifica se existe uma sessão válida no navegador
    Retorna True se autenticado, False caso contrário
    """
    try:
        # Verificar se há dados de sessão no st.session_state
        if st.session_state.authenticated and st.session_state.session:
            return True
        return False
    except Exception as e:
        st.error(f"Erro ao verificar sessão: {str(e)}")
        return False


def logout():
    """Realiza logout do usuário"""
    try:
        if st.session_state.session:
            client = get_supabase_client()
            client.auth.sign_out()
        
        # Limpar sessão
        st.session_state.session = None
        st.session_state.user = None
        st.session_state.authenticated = False
        st.rerun()
    except Exception as e:
        st.error(f"Erro ao fazer logout: {str(e)}")


def get_current_user() -> Optional[Dict[str, Any]]:
    """Retorna o usuário autenticado atual"""
    return st.session_state.user if st.session_state.authenticated else None


def render_html_block(html: str):
    """Renderiza HTML puro, evitando que o parser de markdown quebre a estrutura."""
    if hasattr(st, "html"):
        st.html(html)
    else:
        st.markdown(html, unsafe_allow_html=True)


def apply_login_theme():
    """Aplica CSS personalizado para a página de login"""
    render_html_block("""
    <style>
        /* Ocultar sidebar e elementos do Streamlit */
        [data-testid="stSidebarNav"] { display: none; }
        [data-testid="collapsedControl"] { display: none; }
        .st-emotion-cache-1y4p8pa { display: none; }
        
        /* Configurar página inteira */
        body { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        .stMainBlockContainer {
            background: transparent;
            padding: 0;
        }
        
        .st-emotion-cache-1kyxreq {
            background: transparent;
        }
        
        /* Container principal */
        .login-container {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }
        
        .login-box {
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            width: 100%;
            max-width: 450px;
            padding: 50px 40px;
            text-align: center;
            animation: slideIn 0.5s ease-out;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .login-header {
            margin-bottom: 40px;
        }
        
        .logo-container {
            display: flex;
            justify-content: center;
            margin-bottom: 30px;
            gap: 10px;
            align-items: center;
        }
        
        .logo-circle {
            width: 72px;
            height: 72px;
            background: transparent;
            border-radius: 18px;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            box-shadow: 0 16px 30px rgba(102, 126, 234, 0.22);
        }

        .logo-circle img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }
        
        .login-header h1 {
            font-size: 32px;
            color: #1a1a1a;
            margin: 0;
            font-weight: 700;
            margin-bottom: 8px;
        }
        
        .login-header p {
            font-size: 14px;
            color: #666;
            margin: 0;
            line-height: 1.6;
        }
        
        .divider {
            height: 1px;
            background: #e0e0e0;
            margin: 30px 0;
        }

        .google-login-link {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            width: 100%;
            padding: 14px 18px;
            border: 1px solid #dadce0;
            border-radius: 10px;
            background: #ffffff;
            color: #1f1f1f;
            font-size: 15px;
            font-weight: 600;
            text-decoration: none;
            box-sizing: border-box;
            transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
        }

        .google-login-link:hover {
            background: #f8faff;
            box-shadow: 0 10px 25px rgba(31, 31, 31, 0.08);
            transform: translateY(-1px);
        }

        .google-login-link:visited {
            color: #1f1f1f;
        }

        .google-login-link img,
        .google-login-link svg {
            width: 20px;
            height: 20px;
            flex-shrink: 0;
            display: block;
        }
        
        .info-text {
            font-size: 12px;
            color: #999;
            margin-top: 20px;
            line-height: 1.5;
        }
        
        .footer-text {
            font-size: 11px;
            color: #ccc;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #f0f0f0;
        }
    </style>
    """)


def display_auth_ui():
    """
    Exibe a interface de autenticação com verificação de autorização no banco
    Deve ser chamada no início do app
    """
    initialize_auth_session()
    
    # Processar callback de autenticação
    handle_auth_callback()
    
    # Verificar sessão existente
    if not check_session():
        # Aplicar tema de login
        apply_login_theme()

        oauth_url = get_google_oauth_url()
        logo_src = get_login_logo_src()
        google_icon_src = get_google_icon_src()
        login_action = (
            f'''
            <a class="google-login-link" href="{oauth_url}" target="_self">
                <img src="{google_icon_src}" alt="Google">
                Continuar com Google
            </a>
            '''
            if oauth_url
            else '<div class="info-text">Não foi possível gerar o login agora. Verifique a configuração do Google OAuth.</div>'
        )

        logo_markup = (
            f'<img src="{logo_src}" alt="Midiacode">'
            if logo_src
            else '🔐'
        )

        render_html_block(
            f"""
            <div class="login-container">
                <div class="login-box">
                    <div class="login-header">
                        <div class="logo-container">
                            <div class="logo-circle">{logo_markup}</div>
                        </div>
                        <h1>Ops Manager</h1>
                        <p>Bem-vindo ao seu painel operacional<br>Faça login para continuar</p>
                    </div>
                    <div class="divider"></div>
                    {login_action}
                    <div class="info-text">
                        Use sua conta Google para entrar com segurança e acesso controlado.
                    </div>
                    <div class="footer-text">
                        © 2026 Midiacode. Todos os direitos reservados.
                    </div>
                </div>
            </div>
            """
        )
        
        st.stop()
    
    else:
        user = get_current_user()
        
        if user:
            try:
                client = get_supabase_client()
                
                # Verificar se o usuário está na tabela authorized_users
                response = client.table("authorized_users").select("approved, id").eq(
                    "email", user.email
                ).execute()
                
                authorized_record = response.data[0] if response.data else None
                
                # Usuário não encontrado na tabela
                if not authorized_record:
                    apply_login_theme()
                    render_html_block(f"""
                    <div class="login-container">
                        <div class="login-box">
                            <div style="font-size: 48px; margin-bottom: 20px;">⏳</div>
                            <h1 style="color: #ff9800; margin-bottom: 20px;">Acesso Pendente</h1>
                            <p style="font-size: 15px; line-height: 1.6; margin-bottom: 30px;">
                                Seu email foi registrado com sucesso, mas aguarda aprovação do administrador.
                                <br><br>
                                <strong>{user.email}</strong>
                                <br><br>
                                Você será notificado assim que tiver acesso liberado.
                            </p>
                            <div class="divider"></div>
                        </div>
                    </div>
                    """)
                    
                    col1, col2, col3 = st.columns([1, 1, 1])
                    with col2:
                        if st.button("🚪 Fazer Logout", key="logout_unauthorized", use_container_width=True):
                            logout()
                    
                    st.stop()
                
                # Usuário não aprovado
                if not authorized_record.get("approved", False):
                    apply_login_theme()
                    render_html_block(f"""
                    <div class="login-container">
                        <div class="login-box">
                            <div style="font-size: 48px; margin-bottom: 20px;">⏳</div>
                            <h1 style="color: #ff9800; margin-bottom: 20px;">Acesso em Revisão</h1>
                            <p style="font-size: 15px; line-height: 1.6; margin-bottom: 30px;">
                                Sua conta foi criada com sucesso, mas precisa ser aprovada pelo administrador.
                                <br><br>
                                <strong>{user.email}</strong>
                                <br><br>
                                Você será notificado assim que o acesso for liberado.
                            </p>
                            <div class="divider"></div>
                        </div>
                    </div>
                    """)
                    
                    col1, col2, col3 = st.columns([1, 1, 1])
                    with col2:
                        if st.button("🚪 Fazer Logout", key="logout_pending", use_container_width=True):
                            logout()
                    
                    st.stop()
                
                # Salvar ID do usuário na sessão para uso posterior
                st.session_state.user_id = authorized_record.get("id")
                
                # Atualizar last_login
                client.table("authorized_users").update({
                    "last_login": datetime.utcnow().isoformat()
                }).eq("email", user.email).execute()
                
                # Usuário autorizado e aprovado - Mostrar welcome banner
                user_name = user.user_metadata.get('name', user.email)
                render_html_block(f"""
                <div style="
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px 30px;
                    border-radius: 12px;
                    margin-bottom: 20px;
                    text-align: center;
                ">
                    <h2 style="margin: 0; font-size: 24px; margin-bottom: 5px;">
                        ✅ Bem-vindo, {user_name}!
                    </h2>
                    <p style="margin: 0; font-size: 13px; opacity: 0.9;">
                        Seu acesso foi aprovado. Você pode acessar todas as funcionalidades.
                    </p>
                </div>
                """)
                
                col1, col2, col3 = st.columns([10, 1, 1])
                with col3:
                    if st.button("🚪 Logout", key="logout_btn", use_container_width=True):
                        logout()
                
            except Exception as e:
                st.error(f"❌ Erro ao verificar autorização: {str(e)}")
                st.info("Verifique se a tabela 'authorized_users' foi criada no Supabase")
                col1, col2, col3 = st.columns([1, 1, 1])
                with col2:
                    if st.button("🚪 Logout", key="logout_error"):
                        logout()


def require_auth(func):
    """
    Decorator para proteger funções que requerem autenticação
    """
    def wrapper(*args, **kwargs):
        if not check_session():
            st.error("Você precisa estar autenticado para acessar esta funcionalidade")
            st.stop()
        return func(*args, **kwargs)
    return wrapper
