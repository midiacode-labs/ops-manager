"""
Módulo de autenticação com Supabase (email e senha)
"""

import streamlit as st
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
import base64
import logging
import os
import requests as _requests
from typing import Optional, Dict, Any
from datetime import datetime
from dotenv import load_dotenv
from uuid import uuid4

# Carregar variáveis de ambiente
load_dotenv()

# Configurações do Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
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
    if "auth_feedback" not in st.session_state:
        st.session_state.auth_feedback = None
    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "signin"
    _log_auth(
        logging.DEBUG,
        "initialize_auth_session.done",
        has_feedback=bool(st.session_state.get("auth_feedback")),
    )


def get_login_logo_src() -> Optional[str]:
    """Retorna o icone local da Midiacode como data URI para uso no HTML do login."""
    try:
        with open(ICON_PATH, "rb") as image_file:
            encoded_icon = base64.b64encode(image_file.read()).decode("utf-8")
        return f"data:image/png;base64,{encoded_icon}"
    except OSError:
        return None


def _set_authenticated_state(response: Any) -> None:
    """Atualiza a sessão local após autenticação bem-sucedida."""
    st.session_state.session = getattr(response, "session", None)
    st.session_state.user = getattr(response, "user", None)
    st.session_state.authenticated = bool(
        st.session_state.session and st.session_state.user
    )


def sign_in_with_email_password(email: str, password: str) -> bool:
    """Efetua login no Supabase via email e senha."""
    try:
        client = get_supabase_client()
        response = client.auth.sign_in_with_password(
            {
                "email": email.strip().lower(),
                "password": password,
            }
        )
        _set_authenticated_state(response)
        if not st.session_state.authenticated:
            st.session_state.auth_feedback = {
                "type": "error",
                "message": "Não foi possível iniciar a sessão. Tente novamente.",
            }
            _log_auth(logging.ERROR, "signin.invalid_response", user_email=_mask_email(email))
            return False

        _log_auth(logging.INFO, "signin.success", user_email=_mask_email(email))
        return True
    except Exception as e:
        LOGGER.exception("Falha no login com email e senha")
        _log_auth(logging.ERROR, "signin.error", user_email=_mask_email(email), error=str(e))
        st.session_state.auth_feedback = {
            "type": "error",
            "message": f"Falha ao entrar: {str(e)}",
        }
        return False


def sign_up_with_email_password(name: str, email: str, password: str) -> bool:
    """Cria conta Supabase via email e senha para solicitação de acesso."""
    try:
        client = get_supabase_client()
        response = client.auth.sign_up(
            {
                "email": email.strip().lower(),
                "password": password,
                "options": {
                    "data": {
                        "name": (name or "").strip() or None,
                    }
                },
            }
        )
        _log_auth(
            logging.INFO,
            "signup.success",
            user_email=_mask_email(email),
            has_session=bool(getattr(response, "session", None)),
        )
        st.session_state.auth_feedback = {
            "type": "success",
            "message": (
                "Solicitação enviada com sucesso. "
                "Após confirmar o email (se exigido), aguarde a aprovação "
                "do administrador para acessar o sistema."
            ),
        }
        return True
    except Exception as e:
        LOGGER.exception("Falha no cadastro com email e senha")
        _log_auth(logging.ERROR, "signup.error", user_email=_mask_email(email), error=str(e))
        st.session_state.auth_feedback = {
            "type": "error",
            "message": f"Falha ao criar conta: {str(e)}",
        }
        return False


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
        st.session_state.user_id = None
        st.session_state._supabase_auth_storage = {}
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
        @import url(
            'https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&display=swap'
        );

        /* Ocultar sidebar e elementos do Streamlit */
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="stSidebarNav"] { display: none; }
        [data-testid="collapsedControl"] { display: none; }
        [data-testid="stSidebarCollapsedControl"] { display: none !important; }
        .st-emotion-cache-1y4p8pa { display: none; }

        /* Configurar página inteira */
        body {
            background:
                radial-gradient(circle at 15% 20%, rgba(0, 103, 255, 0.20) 0%, transparent 30%),
                radial-gradient(circle at 85% 10%, rgba(0, 103, 255, 0.16) 0%, transparent 26%),
                linear-gradient(145deg, #f4f8ff 0%, #eaf1ff 42%, #e0ebff 100%);
            min-height: 100vh;
            font-family: 'Manrope', sans-serif;
        }

        html, body, [class*="css"], [data-testid="stAppViewContainer"] {
            font-family: 'Manrope', sans-serif;
        }

        .stMainBlockContainer {
            background: transparent;
            max-width: 1120px;
            padding-top: 0;
            padding-bottom: 0;
        }

        .st-emotion-cache-1kyxreq {
            background: transparent;
        }

        [data-testid="stVerticalBlock"]:has(.login-shell-marker) {
            gap: 0.75rem;
        }

        .login-shell-marker,
        .login-form-marker {
            display: none;
        }

        [data-testid="stVerticalBlock"]:has(.login-shell-marker) {
            margin-top: 72px;
            position: relative;
            overflow: visible;
            padding: 34px 34px 26px 34px;
            border-radius: 28px;
            border: 1px solid rgba(255, 255, 255, 0.72);
            background:
                linear-gradient(
                    180deg,
                    rgba(255, 255, 255, 0.96) 0%,
                    rgba(249, 252, 252, 0.93) 100%
                );
            box-shadow:
                0 28px 70px rgba(0, 103, 255, 0.14),
                inset 0 1px 0 rgba(255, 255, 255, 0.95);
            animation: slideIn 0.5s ease-out;
        }

        [data-testid="stVerticalBlock"]:has(.login-shell-marker)::before {
            content: "";
            position: absolute;
            inset: 0 auto auto 0;
            width: 180px;
            height: 180px;
            background: radial-gradient(circle, rgba(0, 103, 255, 0.18) 0%, transparent 68%);
            pointer-events: none;
            z-index: 0;
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
            position: relative;
            z-index: 1;
            margin-bottom: 22px;
            text-align: center;
        }

        .logo-container {
            display: flex;
            justify-content: center;
            margin-bottom: 22px;
            align-items: center;
        }

        .logo-circle {
            width: 94px;
            height: 94px;
            padding: 16px;
            background: linear-gradient(180deg, #ffffff 0%, #f1fbf9 100%);
            border-radius: 24px;
            border: 1px solid rgba(0, 103, 255, 0.12);
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow:
                0 18px 35px rgba(0, 103, 255, 0.18),
                inset 0 1px 0 rgba(255, 255, 255, 0.9);
        }

        .logo-circle img {
            width: 100%;
            height: 100%;
            object-fit: contain;
            display: block;
        }

        .login-eyebrow {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 12px;
            border-radius: 999px;
            background: rgba(0, 103, 255, 0.10);
            color: #0067ff;
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            margin-bottom: 14px;
        }

        .login-header h1 {
            font-size: 42px;
            color: #0f172a;
            margin: 0;
            font-weight: 800;
            letter-spacing: -0.03em;
            margin-bottom: 10px;
        }

        .login-header p {
            font-size: 16px;
            color: #475569;
            margin: 0;
            line-height: 1.6;
            max-width: 420px;
            margin-left: auto;
            margin-right: auto;
        }

        .divider {
            height: 1px;
            background: linear-gradient(
                90deg,
                rgba(148, 163, 184, 0) 0%,
                rgba(148, 163, 184, 0.45) 18%,
                rgba(148, 163, 184, 0.45) 82%,
                rgba(148, 163, 184, 0) 100%
            );
            margin: 20px 0 18px 0;
        }

        [data-testid="stVerticalBlock"]:has(.login-form-marker) {
            position: relative;
            z-index: 1;
            padding: 0;
            margin-top: 2px;
            background: transparent;
            border: 0;
            box-shadow: none;
        }

        .login-tab-caption {
            margin: 0 0 14px 0;
            color: #64748b;
            font-size: 13px;
            line-height: 1.5;
        }

        .login-helper {
            margin-top: 18px;
            font-size: 12px;
            color: #475569;
            text-align: center;
            line-height: 1.6;
        }

        [data-testid="stForm"] {
            border: none !important;
            background: transparent !important;
            padding: 0 !important;
        }

        [data-testid="stForm"] label,
        [data-testid="stWidgetLabel"] p {
            color: #0f172a !important;
            font-size: 13px !important;
            font-weight: 700 !important;
        }

        [data-testid="stTextInputRootElement"] {
            border-radius: 14px !important;
            background: #f8fbfb !important;
            border: 1px solid #dbe7e7 !important;
            transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
        }

        [data-testid="stTextInputRootElement"]:focus-within {
            border-color: #0067ff !important;
            box-shadow: 0 0 0 4px rgba(0, 103, 255, 0.14) !important;
            background: #ffffff !important;
        }

        [data-testid="stTextInputRootElement"] input {
            color: #0f172a !important;
            font-size: 15px !important;
        }

        [data-testid="stTextInputRootElement"] input::placeholder {
            color: #94a3b8 !important;
        }

        .stButton > button,
        [data-testid="stFormSubmitButton"] button {
            min-height: 50px;
            border: none !important;
            border-radius: 14px !important;
            background: linear-gradient(135deg, #0052cc 0%, #0067ff 100%) !important;
            color: #ffffff !important;
            font-size: 15px !important;
            font-weight: 800 !important;
            letter-spacing: 0.01em;
            box-shadow: 0 14px 28px rgba(0, 103, 255, 0.22);
            transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
        }

        .stButton > button:hover,
        [data-testid="stFormSubmitButton"] button:hover {
            transform: translateY(-1px);
            filter: brightness(1.02);
            box-shadow: 0 18px 34px rgba(0, 103, 255, 0.26);
        }

        .stButton > button:focus,
        [data-testid="stFormSubmitButton"] button:focus {
            box-shadow:
                0 18px 34px rgba(0, 103, 255, 0.26),
                0 0 0 4px rgba(0, 103, 255, 0.18) !important;
        }

        [data-testid="stAlert"] {
            border-radius: 16px !important;
            border: none !important;
        }

        .login-switch-row {
            margin-top: 16px;
            text-align: center;
            color: #64748b;
            font-size: 13px;
            white-space: normal;
            line-height: 1.4;
        }

        .login-switch-row a {
            color: #0067ff;
            font-weight: 800;
            text-decoration: none;
            margin-left: 6px;
            white-space: nowrap;
            display: inline-block;
        }

        .login-switch-row a:hover {
            text-decoration: underline;
        }

        .info-text {
            font-size: 12px;
            color: #999;
            margin-top: 20px;
            line-height: 1.5;
        }

        .footer-text {
            font-size: 11px;
            color: #64748b;
            margin-top: 22px;
            padding-top: 16px;
            border-top: 1px solid rgba(226, 232, 240, 0.92);
            text-align: center;
        }

        @media (max-width: 900px) {
            [data-testid="stVerticalBlock"]:has(.login-shell-marker) {
                margin-top: 28px;
                padding: 24px 18px 18px 18px;
                border-radius: 22px;
            }

            .login-header h1 {
                font-size: 34px;
            }

            .login-header p {
                font-size: 15px;
            }

            .logo-circle {
                width: 82px;
                height: 82px;
                border-radius: 20px;
            }
        }

        @media (max-height: 820px) {
            .stMainBlockContainer {
                padding-top: 8px;
                padding-bottom: 8px;
            }

            [data-testid="stVerticalBlock"]:has(.login-shell-marker) {
                margin-top: 10px;
                padding: 18px 18px 14px 18px;
                border-radius: 22px;
                gap: 0.5rem;
            }

            .login-header {
                margin-bottom: 12px;
            }

            .login-eyebrow {
                margin-bottom: 10px;
                padding: 5px 10px;
                font-size: 11px;
            }

            .logo-container {
                margin-bottom: 14px;
            }

            .logo-circle {
                width: 72px;
                height: 72px;
                padding: 12px;
                border-radius: 18px;
            }

            .login-header h1 {
                font-size: 32px;
                margin-bottom: 6px;
            }

            .login-header p {
                font-size: 14px;
                line-height: 1.45;
                max-width: 360px;
            }

            .divider {
                margin: 12px 0;
            }

            [data-testid="stVerticalBlock"]:has(.login-form-marker) {
                padding: 0;
                margin-top: 0;
            }

            .login-tab-caption {
                margin: 0 0 10px 0;
                font-size: 12px;
                line-height: 1.4;
            }

            [data-testid="stForm"] {
                margin-bottom: 0;
            }

            [data-testid="stWidgetLabel"] {
                margin-bottom: 0.15rem !important;
            }

            [data-testid="stTextInputRootElement"] input {
                font-size: 14px !important;
            }

            .stButton > button,
            [data-testid="stFormSubmitButton"] button {
                min-height: 44px;
                font-size: 14px !important;
            }

            .login-switch-row {
                margin-top: 10px;
                font-size: 12px;
            }

            .login-helper {
                margin-top: 10px;
                font-size: 11px;
                line-height: 1.45;
            }

            .footer-text {
                margin-top: 12px;
                padding-top: 10px;
                font-size: 10px;
            }
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

    requested_mode = st.query_params.get("auth_mode")
    if isinstance(requested_mode, list):
        requested_mode = requested_mode[-1] if requested_mode else None
    if requested_mode in {"signin", "signup"}:
        st.session_state.auth_mode = requested_mode

    def _render_feedback() -> None:
        feedback = st.session_state.get("auth_feedback")
        if not feedback:
            return
        message = feedback.get("message")
        feedback_type = feedback.get("type", "info")
        if feedback_type == "success":
            st.success(message)
        elif feedback_type == "warning":
            st.warning(message)
        elif feedback_type == "error":
            st.error(message)
        else:
            st.info(message)

    # Verificar sessão existente
    if not check_session():
        _log_auth(logging.INFO, "display_auth_ui.not_authenticated")
        apply_login_theme()

        logo_src = get_login_logo_src()
        logo_markup = (
            f'<img src="{logo_src}" alt="Midiacode">'
            if logo_src
            else '🔐'
        )

        _, center_col, _ = st.columns([1, 1.35, 1])
        with center_col:
            auth_mode = st.session_state.get("auth_mode", "signin")
            is_signup_mode = auth_mode == "signup"
            login_panel = st.container()
            with login_panel:
                st.markdown(
                    "<div class='login-shell-marker'></div>",
                    unsafe_allow_html=True,
                )
                render_html_block(
                    f"""
                    <div class="login-header">
                        <div class="login-eyebrow">Acesso seguro</div>
                        <div class="logo-container">
                            <div class="logo-circle">{logo_markup}</div>
                        </div>
                        <h1>Ops Manager</h1>
                        <p>Faça login para continuar<br>
                        ou solicite acesso criando sua conta.</p>
                    </div>
                    """
                )
            _render_feedback()
            st.session_state.auth_feedback = None
            st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
            form_panel = st.container()
            with form_panel:
                st.markdown(
                    "<div class='login-form-marker'></div>",
                    unsafe_allow_html=True,
                )

                if not is_signup_mode:
                    st.markdown(
                        "<p class='login-tab-caption'>Use seu email e senha para "
                        "acessar o painel operacional.</p>",
                        unsafe_allow_html=True,
                    )
                    with st.form("signin_form", clear_on_submit=False):
                        signin_email = st.text_input(
                            "Email",
                            key="signin_email",
                            placeholder="voce@empresa.com",
                        )
                        signin_password = st.text_input(
                            "Senha",
                            type="password",
                            key="signin_password",
                            placeholder="Digite sua senha",
                        )
                        signin_submit = st.form_submit_button(
                            "Entrar",
                            type="primary",
                            use_container_width=True,
                        )

                    if signin_submit:
                        if not signin_email or not signin_password:
                            st.error("Preencha email e senha para entrar.")
                        elif sign_in_with_email_password(signin_email, signin_password):
                            st.rerun()

                    render_html_block(
                        "<div class='login-switch-row'>Não tem acesso ainda?"
                        " <a href='?auth_mode=signup' target='_self'>Solicitar acesso</a>"
                        "</div>"
                    )

                else:
                    st.markdown(
                        "<p class='login-tab-caption'>Crie sua conta para solicitar "
                        "acesso. O login só é liberado após aprovação do administrador.</p>",
                        unsafe_allow_html=True,
                    )
                    with st.form("signup_form", clear_on_submit=False):
                        signup_name = st.text_input(
                            "Nome (opcional)",
                            key="signup_name",
                            placeholder="Como você quer ser identificado",
                        )
                        signup_email = st.text_input(
                            "Email",
                            key="signup_email",
                            placeholder="voce@empresa.com",
                        )
                        signup_password = st.text_input(
                            "Senha",
                            type="password",
                            key="signup_password",
                            placeholder="Crie uma senha segura",
                        )
                        signup_confirm = st.text_input(
                            "Confirmar senha",
                            type="password",
                            key="signup_confirm",
                            placeholder="Repita a senha",
                        )
                        signup_submit = st.form_submit_button(
                            "Criar conta e solicitar acesso",
                            type="primary",
                            use_container_width=True,
                        )

                    if signup_submit:
                        if not signup_email or not signup_password:
                            st.error("Preencha email e senha para concluir o cadastro.")
                        elif len(signup_password) < 6:
                            st.error("A senha deve ter pelo menos 6 caracteres.")
                        elif signup_password != signup_confirm:
                            st.error("As senhas não coincidem.")
                        elif sign_up_with_email_password(
                            signup_name,
                            signup_email,
                            signup_password,
                        ):
                            st.rerun()

                    render_html_block(
                        "<div class='login-switch-row'>Já tem acesso?"
                        " <a href='?auth_mode=signin' target='_self'>Entrar</a>"
                        "</div>"
                    )

            st.markdown(
                "<div class='login-helper'>Somente usuários aprovados pelo "
                "administrador podem acessar o sistema.</div>",
                unsafe_allow_html=True,
            )

            st.markdown(
                "<div class='footer-text'>© 2026 Midiacode. Todos os direitos reservados.</div>",
                unsafe_allow_html=True,
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
                    st.session_state.auth_feedback = {
                        "type": "warning",
                        "message": (
                            "Não foi possível registrar sua solicitação de acesso automaticamente. "
                            "Tente novamente em instantes ou contate o administrador."
                        ),
                    }
                    logout()

                # Se foi criado/identificado como pendente, bloqueia até aprovação.
                if not authorized_record.get("approved", False):
                    _log_auth(
                        logging.WARNING,
                        "display_auth_ui.authorization_pending",
                        user_email=_mask_email(user.email),
                    )
                    st.session_state.auth_feedback = {
                        "type": "warning",
                        "message": (
                            "Acesso pendente de aprovação. "
                            "Sua conta foi criada, mas somente usuários aprovados podem entrar."
                        ),
                    }
                    logout()

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
    """Busca uma imagem de avatar e retorna como data URI base64."""
    try:
        resp = _requests.get(url, timeout=5)
        if resp.status_code == 200:
            mime = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
            encoded = base64.b64encode(resp.content).decode("utf-8")
            return f"data:{mime};base64,{encoded}"
    except Exception:
        pass
    return None


def _get_user_initials(name: Optional[str], email: Optional[str]) -> str:
    """Calcula duas iniciais para uso no avatar placeholder."""
    base_value = (name or "").strip()
    if base_value:
        parts = [chunk for chunk in base_value.split() if chunk]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        if len(parts) == 1:
            return parts[0][:2].upper()

    email_local = (email or "").split("@", 1)[0].strip()
    if not email_local:
        return "US"
    compact = "".join(ch for ch in email_local if ch.isalnum())
    if len(compact) >= 2:
        return compact[:2].upper()
    return (compact + "U").upper()


def _get_avatar_color(seed: str) -> str:
    """Retorna uma cor estável para o avatar a partir de uma seed."""
    palette = [
        "#0f766e",
        "#0ea5e9",
        "#2563eb",
        "#be185d",
        "#b45309",
        "#4f46e5",
        "#166534",
        "#b91c1c",
    ]
    index = sum(ord(char) for char in (seed or "user")) % len(palette)
    return palette[index]


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
        st.page_link("app.py", label="Painel", icon="🏠")
        st.page_link("pages/manage_users.py", label="Gestão de Usuários", icon="👥")
        st.page_link("pages/backup.py", label="Backup", icon="🗄️")

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
            initials = _get_user_initials(user_name, user.email)
            avatar_color = _get_avatar_color(user.email)

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
                        f"""
                        <div style='width:36px;height:36px;border-radius:50%;margin-top:2px;
                        display:flex;align-items:center;justify-content:center;
                        font-size:12px;font-weight:700;color:#ffffff;background:{avatar_color}'>
                        {initials}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            with col_info:
                st.markdown(
                    (
                        f"<div style='font-size:13px;font-weight:600;line-height:1.3'>"
                        f"{user_name}</div>"
                        f"<div style='font-size:11px;color:#888;overflow-wrap:anywhere'>"
                        f"{user.email}</div>"
                    ),
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
