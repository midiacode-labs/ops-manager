"""
Módulo de autenticação com Supabase e Google Login
"""

import streamlit as st
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
import base64
import logging
import os
import requests as _requests
import time
from typing import Optional, Dict, Any
from datetime import datetime
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse, unquote_plus
from uuid import uuid4

# Carregar variáveis de ambiente
load_dotenv()

# Configurações do Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
REDIRECT_URL = os.getenv("STREAMLIT_REDIRECT_URL", "http://localhost:8501")
ICON_PATH = os.path.join(os.path.dirname(__file__), "icone_midiacode.png")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL e SUPABASE_KEY não configurados no .env")


LOGGER = logging.getLogger("ops_manager.auth")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s"
        )
    )
    LOGGER.addHandler(_handler)
LOGGER.setLevel(os.getenv("AUTH_LOG_LEVEL", "INFO").upper())
LOGGER.propagate = False


# Fallback de PKCE para casos em que o Streamlit troca a sessão no retorno OAuth.
PKCE_FALLBACK_TTL_SECONDS = 600
PKCE_FALLBACK_MAX_ITEMS = 20
_pkce_fallback_verifiers: list[dict[str, Any]] = []


def _get_auth_trace_id() -> str:
    """Retorna um identificador de correlação por sessão do Streamlit."""
    if "auth_trace_id" not in st.session_state:
        st.session_state.auth_trace_id = uuid4().hex[:12]
    return st.session_state.auth_trace_id


def _mask_email(email: Optional[str]) -> Optional[str]:
    """Mascara email para logs sem expor PII completa."""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = "*" * len(local)
    else:
        masked_local = f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}"
    return f"{masked_local}@{domain}"


def _log_auth(level: int, event: str, **fields: Any) -> None:
    """Log estruturado do fluxo de autenticação."""
    base_fields = {
        "event": event,
        "trace_id": _get_auth_trace_id(),
        "authenticated": st.session_state.get("authenticated", False),
        "has_session": bool(st.session_state.get("session")),
    }
    base_fields.update(fields)
    payload = " ".join(f"{k}={v}" for k, v in base_fields.items())
    LOGGER.log(level, payload)


def _cleanup_pkce_fallback_cache() -> None:
    """Remove verifiers de fallback expirados ou excedentes."""
    now = time.time()
    valid = [
        item
        for item in _pkce_fallback_verifiers
        if now - item.get("created_at", 0) <= PKCE_FALLBACK_TTL_SECONDS
    ]
    if len(valid) > PKCE_FALLBACK_MAX_ITEMS:
        valid = valid[-PKCE_FALLBACK_MAX_ITEMS:]
    _pkce_fallback_verifiers.clear()
    _pkce_fallback_verifiers.extend(valid)


def _store_pkce_fallback_verifier(code_verifier: str) -> None:
    """Armazena verifier em cache de processo para fallback de callback OAuth."""
    _cleanup_pkce_fallback_cache()
    _pkce_fallback_verifiers.append(
        {
            "code_verifier": code_verifier,
            "created_at": time.time(),
            "trace_id": _get_auth_trace_id(),
        }
    )
    _log_auth(
        logging.DEBUG,
        "pkce_fallback_cache.store",
        cache_size=len(_pkce_fallback_verifiers),
    )


def _consume_pkce_fallback_verifier() -> Optional[str]:
    """Obtém o verifier mais recente do cache de fallback."""
    _cleanup_pkce_fallback_cache()
    if not _pkce_fallback_verifiers:
        return None
    item = _pkce_fallback_verifiers.pop()
    _log_auth(
        logging.WARNING,
        "pkce_fallback_cache.consume",
        source_trace_id=item.get("trace_id"),
        cache_size=len(_pkce_fallback_verifiers),
    )
    return _normalize_query_param(item.get("code_verifier"))


def get_supabase_client() -> Client:
    """Retorna uma instância do cliente Supabase"""
    _log_auth(logging.DEBUG, "get_supabase_client")
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
    _log_auth(logging.DEBUG, "initialize_auth_session.start")
    if "session" not in st.session_state:
        st.session_state.session = None
    if "user" not in st.session_state:
        st.session_state.user = None
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "_supabase_auth_storage" not in st.session_state:
        st.session_state._supabase_auth_storage = {}
    if "auth_callback_error" not in st.session_state:
        st.session_state.auth_callback_error = None
    if "pending_pkce_code_verifier" not in st.session_state:
        st.session_state.pending_pkce_code_verifier = None
    _log_auth(
        logging.DEBUG,
        "initialize_auth_session.done",
        has_auth_callback_error=bool(st.session_state.get("auth_callback_error")),
        has_pending_pkce=bool(st.session_state.get("pending_pkce_code_verifier")),
    )


def get_google_oauth_url() -> str:
    """Gera a URL de login do Google através do Supabase"""
    try:
        _log_auth(logging.INFO, "oauth_url_generation.start", redirect_to=REDIRECT_URL)
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
        if code_verifier:
            st.session_state.pending_pkce_code_verifier = code_verifier
            _store_pkce_fallback_verifier(code_verifier)
            _log_auth(logging.INFO, "oauth_url_generation.pkce_verifier_stored")
        else:
            _log_auth(logging.WARNING, "oauth_url_generation.pkce_verifier_missing")

        if response and response.url and code_verifier:
            _log_auth(logging.INFO, "oauth_url_generation.success", has_response_url=True)
            return append_query_params(
                response.url,
                {
                    "redirect_to": append_query_params(
                        redirect_to,
                        {"pkce_code_verifier": code_verifier},
                    )
                },
            )
        _log_auth(
            logging.WARNING,
            "oauth_url_generation.partial",
            has_response=bool(response),
            has_response_url=bool(response and response.url),
        )
        return response.url if response else None
    except Exception as e:
        LOGGER.exception("Falha ao gerar URL OAuth")
        _log_auth(logging.ERROR, "oauth_url_generation.error", error=str(e))
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


def _normalize_query_param(value: Any) -> Optional[str]:
    """Normaliza parâmetros de query do Streamlit para string não vazia."""
    if value is None:
        return None
    if isinstance(value, list):
        value = value[-1] if value else None
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


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
    query_keys = sorted(list(query_params.keys()))
    _log_auth(logging.INFO, "auth_callback.received", query_keys=query_keys)
    
    code = _normalize_query_param(query_params.get("code"))
    if code:
        try:
            _log_auth(logging.INFO, "auth_callback.code_found", code_length=len(code))
            client = get_supabase_client()
            code_verifier = _normalize_query_param(
                query_params.get("pkce_code_verifier")
            )
            verifier_source = "query"

            if not code_verifier:
                code_verifier = _normalize_query_param(
                    st.session_state.get("pending_pkce_code_verifier")
                )
                verifier_source = "session"

            if not code_verifier:
                code_verifier = _normalize_query_param(
                    client.auth._storage.get_item(
                        f"{client.auth._storage_key}-code-verifier"
                    )
                )
                verifier_source = "storage"

            if not code_verifier:
                code_verifier = _consume_pkce_fallback_verifier()
                verifier_source = "process_fallback"

            _log_auth(
                logging.INFO,
                "auth_callback.verifier_lookup",
                verifier_source=verifier_source,
                has_code_verifier=bool(code_verifier),
            )

            if not code_verifier:
                _log_auth(logging.ERROR, "auth_callback.verifier_missing")
                st.session_state.auth_callback_error = (
                    "Falha ao concluir o login com Google. "
                    "O verificador de segurança (PKCE) não foi encontrado no retorno. "
                    "Clique em 'Continuar com Google' novamente para gerar um novo login."
                )
                st.query_params.clear()
                st.rerun()
            
            # Troca o código por uma sessão
            exchange_payload = {
                "auth_code": code,
                "code_verifier": code_verifier,
            }

            _log_auth(logging.INFO, "auth_callback.exchange.start")

            response = client.auth.exchange_code_for_session(exchange_payload)
            
            if response:
                masked_email = _mask_email(getattr(response.user, "email", None))
                _log_auth(
                    logging.INFO,
                    "auth_callback.exchange.success",
                    user_email=masked_email,
                )
                st.session_state.session = response.session
                st.session_state.user = response.user
                st.session_state.authenticated = True
                st.session_state.auth_callback_error = None
                st.session_state.pending_pkce_code_verifier = None
                
                # Limpar parâmetros de query
                st.query_params.clear()
                st.rerun()
            else:
                _log_auth(logging.ERROR, "auth_callback.exchange.empty_response")
                st.session_state.auth_callback_error = (
                    "Não foi possível finalizar a autenticação. Tente novamente em instantes."
                )
                st.query_params.clear()
                st.rerun()
                
        except Exception as e:
            LOGGER.exception("Falha ao processar callback OAuth")
            _log_auth(logging.ERROR, "auth_callback.exchange.error", error=str(e))
            st.session_state.auth_callback_error = (
                "Falha ao processar o retorno do login. "
                f"Detalhes técnicos: {str(e)}"
            )
            st.query_params.clear()
            st.rerun()

    if "error" in query_params:
        error = query_params.get("error")
        error_code = query_params.get("error_code")
        raw_description = query_params.get("error_description", "")
        error_description = unquote_plus(raw_description) if raw_description else ""
        _log_auth(
            logging.WARNING,
            "auth_callback.provider_error",
            error=error,
            error_code=error_code,
            has_error_description=bool(error_description),
        )

        if error_code == "signup_disabled":
            st.session_state.auth_callback_error = (
                "Seu acesso ainda não está liberado. Esta aplicação permite apenas usuários "
                "previamente autorizados. Solicite aprovação ao administrador e tente novamente."
            )
        elif error == "access_denied":
            st.session_state.auth_callback_error = (
                "Não foi possível concluir o login porque o acesso foi negado "
                "pelo provedor de autenticação."
            )
        else:
            st.session_state.auth_callback_error = (
                "Não foi possível concluir o login no momento. "
                f"Detalhes: {error_description or 'erro desconhecido.'}"
            )

        # Limpa os parâmetros para evitar repetir o mesmo erro no próximo rerun.
        st.query_params.clear()
        st.rerun()


def check_session():
    """
    Verifica se existe uma sessão válida no navegador
    Retorna True se autenticado, False caso contrário
    """
    try:
        # Verificar se há dados de sessão no st.session_state
        if st.session_state.authenticated and st.session_state.session:
            _log_auth(logging.DEBUG, "check_session.valid")
            return True
        _log_auth(logging.DEBUG, "check_session.invalid")
        return False
    except Exception as e:
        LOGGER.exception("Erro ao verificar sessão")
        _log_auth(logging.ERROR, "check_session.error", error=str(e))
        st.error(f"Erro ao verificar sessão: {str(e)}")
        return False


def ensure_pending_user_record(client: Client, user: Any) -> Optional[Dict[str, Any]]:
    """Garante que o usuário autenticado exista na tabela authorized_users como pendente."""
    try:
        response = (
            client.table("authorized_users")
            .select("id, approved")
            .eq("email", user.email)
            .execute()
        )
        existing_record = response.data[0] if response.data else None
        if existing_record:
            _log_auth(
                logging.INFO,
                "authorization.ensure_pending.already_exists",
                user_email=_mask_email(user.email),
                approved=existing_record.get("approved", False),
            )
            return existing_record

        user_name = None
        user_metadata = getattr(user, "user_metadata", None)
        if isinstance(user_metadata, dict):
            user_name = user_metadata.get("name")

        client.table("authorized_users").insert(
            {
                "email": user.email,
                "name": user_name,
                "approved": False,
            }
        ).execute()
        _log_auth(
            logging.INFO,
            "authorization.ensure_pending.inserted",
            user_email=_mask_email(user.email),
        )

        response = (
            client.table("authorized_users")
            .select("id, approved")
            .eq("email", user.email)
            .execute()
        )
        ensured_record = response.data[0] if response.data else None
        _log_auth(
            logging.INFO,
            "authorization.ensure_pending.recheck",
            user_email=_mask_email(user.email),
            found=bool(ensured_record),
        )
        return ensured_record
    except Exception as e:
        LOGGER.exception("Erro ao registrar usuário pendente")
        _log_auth(
            logging.ERROR,
            "authorization.ensure_pending.error",
            user_email=_mask_email(getattr(user, "email", None)),
            error=str(e),
        )
        return None


def logout():
    """Realiza logout do usuário"""
    try:
        masked_email = _mask_email(
            getattr(st.session_state.get("user"), "email", None)
            if st.session_state.get("user")
            else None
        )
        _log_auth(logging.INFO, "logout.start", user_email=masked_email)
        if st.session_state.session:
            client = get_supabase_client()
            client.auth.sign_out()
            _log_auth(logging.INFO, "logout.supabase_signout.success")
        else:
            _log_auth(logging.INFO, "logout.no_session")
        
        # Limpar sessão
        st.session_state.session = None
        st.session_state.user = None
        st.session_state.authenticated = False
        st.session_state.auth_callback_error = None
        st.session_state.pending_pkce_code_verifier = None
        _log_auth(logging.INFO, "logout.done")
        st.rerun()
    except Exception as e:
        LOGGER.exception("Erro ao fazer logout")
        _log_auth(logging.ERROR, "logout.error", error=str(e))
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
    _log_auth(logging.DEBUG, "display_auth_ui.start")
    initialize_auth_session()
    
    # Processar callback de autenticação
    handle_auth_callback()
    
    # Verificar sessão existente
    if not check_session():
        _log_auth(logging.INFO, "display_auth_ui.not_authenticated")
        # Aplicar tema de login
        apply_login_theme()

        auth_callback_error = st.session_state.get("auth_callback_error")
        callback_error_markup = (
            f"""
            <div style="background:#fff4e5;border:1px solid #ffd8a8;color:#7a4b00;
            border-radius:10px;padding:12px 14px;margin:0 0 18px 0;font-size:14px;line-height:1.5;">
                <strong>⚠️ Atenção:</strong><br>{auth_callback_error}
            </div>
            """
            if auth_callback_error
            else ""
        )

        oauth_url = get_google_oauth_url()
        _log_auth(logging.INFO, "display_auth_ui.login_screen", has_oauth_url=bool(oauth_url))
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
                    {callback_error_markup}
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
                _log_auth(
                    logging.INFO,
                    "display_auth_ui.authenticated",
                    user_email=_mask_email(user.email),
                )
                client = get_supabase_client()
                
                # Verificar se o usuário está na tabela authorized_users
                response = client.table("authorized_users").select("approved, id").eq(
                    "email", user.email
                ).execute()
                
                authorized_record = response.data[0] if response.data else None
                _log_auth(
                    logging.INFO,
                    "display_auth_ui.authorization_lookup",
                    found=bool(authorized_record),
                )
                
                # Usuário não encontrado na tabela
                if not authorized_record:
                    authorized_record = ensure_pending_user_record(client, user)

                if not authorized_record:
                    _log_auth(
                        logging.WARNING,
                        "display_auth_ui.authorization_pending_registration_failed",
                        user_email=_mask_email(user.email),
                    )
                    apply_login_theme()
                    render_html_block(f"""
                    <div class="login-container">
                        <div class="login-box">
                            <div style="font-size: 48px; margin-bottom: 20px;">⏳</div>
                            <h1 style="color: #ff9800; margin-bottom: 20px;">Acesso Pendente</h1>
                            <p style="font-size: 15px; line-height: 1.6; margin-bottom: 30px;">
                                Sua autenticação foi concluída, mas não foi possível registrar sua solicitação de acesso automaticamente.
                                <br><br>
                                <strong>{user.email}</strong>
                                <br><br>
                                Tente novamente em instantes ou contate o administrador para concluir o cadastro manualmente.
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

                # Se foi criado/identificado como pendente, bloqueia até aprovação.
                if not authorized_record.get("approved", False):
                    _log_auth(
                        logging.WARNING,
                        "display_auth_ui.authorization_pending",
                        user_email=_mask_email(user.email),
                    )
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
                
                # Salvar ID do usuário na sessão para uso posterior
                st.session_state.user_id = authorized_record.get("id")
                _log_auth(
                    logging.INFO,
                    "display_auth_ui.authorization_approved",
                    user_id=authorized_record.get("id"),
                )
                
                # Atualizar last_login
                client.table("authorized_users").update({
                    "last_login": datetime.utcnow().isoformat()
                }).eq("email", user.email).execute()
                _log_auth(logging.INFO, "display_auth_ui.last_login_updated")
                
                # Renderizar sidebar padrão com navegação e logout
                render_sidebar()
                
            except Exception as e:
                LOGGER.exception("Erro ao verificar autorização do usuário")
                _log_auth(logging.ERROR, "display_auth_ui.authorization_error", error=str(e))
                st.error(f"❌ Erro ao verificar autorização: {str(e)}")
                st.info("Verifique se a tabela 'authorized_users' foi criada no Supabase")
                with st.sidebar:
                    if st.button("🚪 Sair", key="logout_error", use_container_width=True):
                        logout()


def _fetch_avatar_base64(url: str) -> Optional[str]:
    """Busca o avatar do Google e retorna como data URI base64."""
    try:
        resp = _requests.get(url, timeout=5)
        if resp.status_code == 200:
            mime = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
            encoded = base64.b64encode(resp.content).decode("utf-8")
            return f"data:{mime};base64,{encoded}"
    except Exception:
        pass
    return None


def render_sidebar():
    """
    Renderiza o sidebar padrão da aplicação para usuários autenticados.
    Inclui logo, título, navegação com ícones e informações do usuário com logout.
    """
    _log_auth(logging.DEBUG, "render_sidebar.start")
    st.logo(ICON_PATH, link="https://midiacode.com/")

    with st.sidebar:
        # Ocultar a navegação automática do Streamlit
        st.markdown(
            """
            <style>
            [data-testid="stSidebarNav"] { display: none !important; }
            </style>
            """,
            unsafe_allow_html=True,
        )

        # Título da aplicação
        st.markdown(
            "<div style='font-size:17px;font-weight:700;"
            "color:#0067ff;line-height:1.2'>Ops Manager</div>"
            "<div style='font-size:11px;color:#888;margin-top:2px'>Midiacode</div>",
            unsafe_allow_html=True,
        )

        st.divider()

        # Navegação
        st.page_link("app.py", label="Painel de Sandbox", icon="🏠")
        st.page_link("pages/manage_users.py", label="Gestão de Usuários", icon="👥")

        st.divider()

        # Informações do usuário + logout
        user = get_current_user()
        if user:
            _log_auth(
                logging.DEBUG,
                "render_sidebar.user_present",
                user_email=_mask_email(user.email),
            )
            user_name = user.user_metadata.get("name", user.email)
            photo_url = user.user_metadata.get("picture")
            avatar_src = _fetch_avatar_base64(photo_url) if photo_url else None

            col_photo, col_info = st.columns([1, 3])
            with col_photo:
                if avatar_src:
                    st.markdown(
                        f'<img src="{avatar_src}" style="width:36px;height:36px;'
                        'border-radius:50%;margin-top:2px">',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        "<div style='font-size:28px;line-height:1'>👤</div>",
                        unsafe_allow_html=True,
                    )
            with col_info:
                st.markdown(
                    f"<div style='font-size:13px;font-weight:600;line-height:1.3'>{user_name}</div>"
                    f"<div style='font-size:11px;color:#888;overflow-wrap:anywhere'>{user.email}</div>",
                    unsafe_allow_html=True,
                )

            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

            st.button(
                "🚪 Sair",
                key="sidebar_logout",
                use_container_width=True,
                on_click=logout,
            )


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
