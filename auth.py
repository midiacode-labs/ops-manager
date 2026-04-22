"""
Módulo de autenticação com Supabase (email e senha)
"""

import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
import base64
import json
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
REDIRECT_URL = os.getenv("STREAMLIT_REDIRECT_URL", "http://localhost:8501")
ICON_PATH = os.path.join(os.path.dirname(__file__), "icone_midiacode.png")
AUTH_LOCAL_STORAGE_KEY = "ops_manager_auth_tokens_v1"
AUTH_QUERY_ACCESS_TOKEN_KEY = "auth_access_token"
AUTH_QUERY_REFRESH_TOKEN_KEY = "auth_refresh_token"

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
    client = create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=ClientOptions(storage=StreamlitSessionStorage()),
    )
    # create_client() tenta recuperar a sessão do storage para definir o JWT
    # nos headers do PostgREST. Se essa recuperação falhar silenciosamente
    # (ex.: token expirado sem refresh bem-sucedido), o cliente cai de volta
    # para a anon key, e operações restritas por RLS (como UPDATE) retornam
    # 0 linhas sem lançar exceção. O fallback abaixo garante que o JWT seja
    # definido a partir da sessão já validada em st.session_state.
    anon_auth_header = f"Bearer {SUPABASE_KEY}"
    if client.options.headers.get("Authorization") == anon_auth_header:
        session = st.session_state.get("session")
        if session:
            access_token = getattr(session, "access_token", None)
            if access_token:
                _log_auth(
                    logging.WARNING,
                    "get_supabase_client.session_recovery_fallback",
                )
                client.options.headers["Authorization"] = f"Bearer {access_token}"
    return client


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
    if "recovery_tokens" not in st.session_state:
        st.session_state.recovery_tokens = None
    if "show_reset_request" not in st.session_state:
        st.session_state.show_reset_request = False
    if "auth_tokens_from_query" not in st.session_state:
        st.session_state.auth_tokens_from_query = None
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


def _normalize_query_param(value: Any) -> Optional[str]:
    """Normaliza parâmetros de query para string não vazia."""
    if value is None:
        return None
    if isinstance(value, list):
        value = value[-1] if value else None
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _hydrate_recovery_tokens_from_hash() -> None:
    """Converte hash de recuperação do Supabase em query params acessíveis no backend."""
    components.html(
        """
        <script>
        (function() {
            const root = window.parent && window.parent !== window ? window.parent : window;
            const hash = root.location.hash || "";
            if (!hash || hash.length <= 1) {
                return;
            }

            const hashParams = new URLSearchParams(hash.substring(1));
            const accessToken = hashParams.get("access_token");
            const refreshToken = hashParams.get("refresh_token");
            const flowType = hashParams.get("type");

            if (!accessToken || !refreshToken || flowType !== "recovery") {
                return;
            }

            const target = new URL(root.location.href);
            target.hash = "";
            target.searchParams.set("recovery_access_token", accessToken);
            target.searchParams.set("recovery_refresh_token", refreshToken);
            target.searchParams.set("recovery_type", flowType);
            root.location.replace(target.toString());
        })();
        </script>
        """,
        height=0,
        width=0,
    )


def _capture_recovery_tokens_from_query() -> None:
    """Lê tokens de recuperação da URL e persiste em sessão para troca de senha."""
    query_params = st.query_params
    recovery_type = _normalize_query_param(query_params.get("recovery_type"))
    access_token = _normalize_query_param(query_params.get("recovery_access_token"))
    refresh_token = _normalize_query_param(query_params.get("recovery_refresh_token"))

    if recovery_type == "recovery" and access_token and refresh_token:
        st.session_state.recovery_tokens = {
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
        st.session_state.auth_mode = "signin"
        st.session_state.auth_feedback = {
            "type": "info",
            "message": "Token de recuperação recebido. Defina sua nova senha abaixo.",
        }
        st.query_params.clear()
        st.rerun()


def _extract_session_tokens(session: Any) -> Optional[Dict[str, str]]:
    """Extrai access/refresh token da sessão retornada pelo Supabase."""
    if not session:
        return None

    if isinstance(session, dict):
        access_token = session.get("access_token")
        refresh_token = session.get("refresh_token")
    else:
        access_token = getattr(session, "access_token", None)
        refresh_token = getattr(session, "refresh_token", None)

    if not access_token or not refresh_token:
        return None

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


def _persist_session_tokens_in_local_storage(session: Any) -> None:
    """Persiste tokens da sessão no localStorage do navegador."""
    tokens = _extract_session_tokens(session)
    if not tokens:
        return

    payload = json.dumps(tokens)
    payload_js = json.dumps(payload)
    storage_key_js = json.dumps(AUTH_LOCAL_STORAGE_KEY)
    components.html(
        f"""
        <script>
        (function() {{
            try {{
                const root = window.parent && window.parent !== window ? window.parent : window;
                const targets = [root, window];
                for (const target of targets) {{
                    try {{
                        target.localStorage.setItem({storage_key_js}, {payload_js});
                    }} catch (error) {{}}
                    try {{
                        target.sessionStorage.setItem({storage_key_js}, {payload_js});
                    }} catch (error) {{}}
                }}
            }} catch (error) {{
                // Mantém o fluxo de login funcional mesmo sem acesso ao storage.
            }}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def _clear_session_tokens_from_local_storage() -> None:
    """Remove tokens persistidos localmente no navegador."""
    storage_key_js = json.dumps(AUTH_LOCAL_STORAGE_KEY)
    components.html(
        f"""
        <script>
        (function() {{
            try {{
                const root = window.parent && window.parent !== window ? window.parent : window;
                const targets = [root, window];
                for (const target of targets) {{
                    try {{
                        target.localStorage.removeItem({storage_key_js});
                    }} catch (error) {{}}
                    try {{
                        target.sessionStorage.removeItem({storage_key_js});
                    }} catch (error) {{}}
                }}
            }} catch (error) {{
                // Não bloqueia o logout caso localStorage esteja indisponível.
            }}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def _hydrate_auth_tokens_from_local_storage() -> None:
    """Converte tokens do localStorage em query params consumíveis no backend."""
    if st.session_state.get("authenticated"):
        return

    if st.session_state.get("auth_tokens_from_query"):
        return

    storage_key_js = json.dumps(AUTH_LOCAL_STORAGE_KEY)
    components.html(
        f"""
        <script>
        (function() {{
            try {{
                const root = window.parent && window.parent !== window ? window.parent : window;

                const decodeJwtPayload = (token) => {{
                    const parts = (token || "").split(".");
                    if (parts.length < 2) return null;
                    const normalized = parts[1].replace(/-/g, "+").replace(/_/g, "/");
                    const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
                    return JSON.parse(root.atob(padded));
                }};

                const target = new URL(root.location.href);
                const hasAccess = !!target.searchParams.get("auth_access_token");
                const hasRefresh = !!target.searchParams.get("auth_refresh_token");
                if (hasAccess || hasRefresh) {{
                    return;
                }}

                const readFromStorage = () => {{
                    const targets = [root, window];
                    for (const target of targets) {{
                        try {{
                            const value = target.localStorage.getItem({storage_key_js});
                            if (value) return value;
                        }} catch (error) {{}}
                        try {{
                            const value = target.sessionStorage.getItem({storage_key_js});
                            if (value) return value;
                        }} catch (error) {{}}
                    }}
                    return null;
                }};

                const payload = readFromStorage();
                if (!payload) {{
                    return;
                }}

                const parsed = JSON.parse(payload);
                if (!parsed || !parsed.access_token || !parsed.refresh_token) {{
                    return;
                }}

                target.searchParams.set("auth_access_token", parsed.access_token);
                target.searchParams.set("auth_refresh_token", parsed.refresh_token);
                root.location.replace(target.toString());
            }} catch (error) {{
                // Não interrompe renderização caso parsing/storage falhe.
            }}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def _capture_auth_tokens_from_query() -> None:
    """Captura tokens de auth vindos da URL e persiste temporariamente na sessão."""
    # Se já autenticado, a sessão já está ativa — não roda novamente para
    # evitar forçar um rerun que descartaria o estado de botões Streamlit.
    if st.session_state.get("authenticated"):
        return

    query_params = st.query_params
    access_token = _normalize_query_param(query_params.get(AUTH_QUERY_ACCESS_TOKEN_KEY))
    refresh_token = _normalize_query_param(query_params.get(AUTH_QUERY_REFRESH_TOKEN_KEY))

    if access_token and refresh_token:
        incoming_tokens = {
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
        if st.session_state.get("auth_tokens_from_query") != incoming_tokens:
            st.session_state.auth_tokens_from_query = incoming_tokens
            st.rerun()


def _persist_session_tokens_in_query_params(session: Any) -> None:
    """Mantém tokens na URL para restaurar sessão após refresh de página."""
    tokens = _extract_session_tokens(session)
    if not tokens:
        return

    current_access = _normalize_query_param(st.query_params.get(AUTH_QUERY_ACCESS_TOKEN_KEY))
    current_refresh = _normalize_query_param(st.query_params.get(AUTH_QUERY_REFRESH_TOKEN_KEY))
    if current_access == tokens["access_token"] and current_refresh == tokens["refresh_token"]:
        return

    st.query_params[AUTH_QUERY_ACCESS_TOKEN_KEY] = tokens["access_token"]
    st.query_params[AUTH_QUERY_REFRESH_TOKEN_KEY] = tokens["refresh_token"]


def _restore_session_from_local_storage_tokens() -> bool:
    """Tenta restaurar sessão Supabase a partir de tokens capturados da URL."""
    tokens = st.session_state.get("auth_tokens_from_query")
    if not tokens:
        return False

    try:
        client = get_supabase_client()
        set_session_method = getattr(client.auth, "set_session", None)
        if not callable(set_session_method):
            raise RuntimeError("Método set_session não disponível no cliente Supabase")

        response = set_session_method(
            tokens["access_token"],
            tokens["refresh_token"],
        )
        _set_authenticated_state(response)

        if not st.session_state.authenticated:
            _sync_authenticated_state_from_client(client)

        if st.session_state.authenticated:
            _persist_session_tokens_in_local_storage(st.session_state.session)
            _log_auth(logging.INFO, "signin.session_restored_from_local_storage")
            st.session_state.auth_tokens_from_query = None
            return True

        _log_auth(logging.WARNING, "signin.local_storage_restore_invalid_response")
    except Exception as e:
        _log_auth(
            logging.WARNING,
            "signin.local_storage_restore_error",
            error=str(e),
        )

    st.session_state.auth_tokens_from_query = None
    _clear_session_tokens_from_local_storage()
    return False


def request_password_reset(email: str) -> bool:
    """Solicita envio do email de recuperação de senha."""
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        st.session_state.auth_feedback = {
            "type": "error",
            "message": "Informe seu email para receber o link de recuperação.",
        }
        return False

    try:
        client = get_supabase_client()
        reset_method = getattr(client.auth, "reset_password_for_email", None)
        if callable(reset_method):
            try:
                reset_method(normalized_email, {"redirect_to": REDIRECT_URL})
            except TypeError:
                reset_method(
                    {
                        "email": normalized_email,
                        "options": {"redirect_to": REDIRECT_URL},
                    }
                )
        else:
            legacy_method = getattr(client.auth, "reset_password_email", None)
            if not callable(legacy_method):
                raise RuntimeError("Método de reset de senha não disponível no cliente Supabase")
            try:
                legacy_method(normalized_email, {"redirect_to": REDIRECT_URL})
            except TypeError:
                legacy_method(
                    {
                        "email": normalized_email,
                        "options": {"redirect_to": REDIRECT_URL},
                    }
                )

        _log_auth(
            logging.INFO,
            "password_reset.requested",
            user_email=_mask_email(normalized_email),
        )
        st.session_state.auth_feedback = {
            "type": "success",
            "message": (
                "Enviamos um link para redefinição de senha. "
                "Abra o email e clique no link para continuar no ambiente local."
            ),
        }
        return True
    except Exception as e:
        error_msg = str(e).lower()
        LOGGER.exception("Falha ao solicitar reset de senha")
        _log_auth(
            logging.ERROR,
            "password_reset.request_error",
            user_email=_mask_email(normalized_email),
            error=str(e),
        )
        if "rate limit" in error_msg or "too many requests" in error_msg:
            st.session_state.auth_feedback = {
                "type": "warning",
                "message": (
                    "Você solicitou a recuperação muitas vezes seguidas. "
                    "Por favor, aguarde alguns instantes e tente novamente."
                ),
            }
        else:
            st.session_state.auth_feedback = {
                "type": "error",
                "message": (
                    "Não foi possível enviar o email de recuperação. "
                    "Confirme se o redirect URL está permitido no Supabase."
                ),
            }
        return False


def complete_password_reset(new_password: str, confirm_password: str) -> bool:
    """Conclui a troca de senha usando tokens de recuperação."""
    recovery_tokens = st.session_state.get("recovery_tokens")
    if not recovery_tokens:
        st.session_state.auth_feedback = {
            "type": "error",
            "message": "Nenhum token de recuperação ativo. Solicite um novo email.",
        }
        return False

    if not new_password or not confirm_password:
        st.session_state.auth_feedback = {
            "type": "error",
            "message": "Preencha e confirme a nova senha.",
        }
        return False

    if len(new_password) < 6:
        st.session_state.auth_feedback = {
            "type": "error",
            "message": "A nova senha deve ter pelo menos 6 caracteres.",
        }
        return False

    if new_password != confirm_password:
        st.session_state.auth_feedback = {
            "type": "error",
            "message": "As senhas informadas não coincidem.",
        }
        return False

    try:
        client = get_supabase_client()
        set_session_method = getattr(client.auth, "set_session", None)
        if not callable(set_session_method):
            raise RuntimeError("Método set_session não disponível no cliente Supabase")

        set_session_method(
            recovery_tokens["access_token"],
            recovery_tokens["refresh_token"],
        )

        update_method = getattr(client.auth, "update_user", None)
        if not callable(update_method):
            raise RuntimeError("Método update_user não disponível no cliente Supabase")

        update_method({"password": new_password})

        st.session_state.recovery_tokens = None
        st.session_state.auth_feedback = {
            "type": "success",
            "message": "Senha redefinida com sucesso. Faça login com a nova senha.",
        }
        logout()
        return True
    except Exception as e:
        LOGGER.exception("Falha ao concluir reset de senha")
        _log_auth(logging.ERROR, "password_reset.complete_error", error=str(e))
        st.session_state.auth_feedback = {
            "type": "error",
            "message": "Não foi possível redefinir a senha. Solicite um novo link.",
        }
        return False


def _set_authenticated_state(response: Any) -> None:
    """Atualiza a sessão local após autenticação bem-sucedida."""
    session_obj = getattr(response, "session", None) if response is not None else None
    user_obj = getattr(response, "user", None) if response is not None else None

    if not user_obj and session_obj is not None:
        user_obj = getattr(session_obj, "user", None)

    if not session_obj and response is not None and hasattr(response, "access_token"):
        session_obj = response
        if not user_obj:
            user_obj = getattr(response, "user", None)

    st.session_state.session = session_obj
    st.session_state.user = user_obj
    st.session_state.authenticated = bool(
        st.session_state.session and st.session_state.user
    )
    if st.session_state.authenticated:
        _persist_session_tokens_in_local_storage(st.session_state.session)
        _persist_session_tokens_in_query_params(st.session_state.session)


def _sync_authenticated_state_from_client(client: Client) -> bool:
    """Sincroniza sessão e usuário usando métodos de leitura do cliente Supabase."""
    session_obj = None
    user_obj = None

    try:
        get_session_method = getattr(client.auth, "get_session", None)
        if callable(get_session_method):
            session_resp = get_session_method()
            session_obj = getattr(session_resp, "session", None)
            if session_obj is None and hasattr(session_resp, "access_token"):
                session_obj = session_resp
    except Exception as e:
        _log_auth(logging.DEBUG, "signin.sync_get_session_error", error=str(e))

    try:
        get_user_method = getattr(client.auth, "get_user", None)
        if callable(get_user_method):
            user_resp = get_user_method()
            user_obj = getattr(user_resp, "user", None)
    except Exception as e:
        _log_auth(logging.DEBUG, "signin.sync_get_user_error", error=str(e))

    if not user_obj and session_obj is not None:
        user_obj = getattr(session_obj, "user", None)

    st.session_state.session = session_obj
    st.session_state.user = user_obj
    st.session_state.authenticated = bool(session_obj and user_obj)

    if st.session_state.authenticated:
        _persist_session_tokens_in_local_storage(session_obj)
        _persist_session_tokens_in_query_params(session_obj)

    return st.session_state.authenticated


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
        error_msg = str(e).lower()
        LOGGER.exception("Falha no login com email e senha")
        _log_auth(logging.ERROR, "signin.error", user_email=_mask_email(email), error=str(e))
        if "rate limit" in error_msg or "too many requests" in error_msg:
            st.session_state.auth_feedback = {
                "type": "warning",
                "message": (
                    "Por motivo de segurança, o acesso foi bloqueado "
                    "temporariamente (muitas tentativas). Tente novamente "
                    "em alguns minutos."
                ),
            }
        else:
            st.session_state.auth_feedback = {
                "type": "error",
                "message": f"Falha ao entrar: {str(e)}",
            }
        return False


def sign_up_with_email_password(name: str, email: str, password: str) -> bool:
    """Cria conta Supabase via email e senha para solicitação de acesso."""
    try:
        normalized_email = (email or "").strip().lower()
        normalized_name = (name or "").strip() or None
        client = get_supabase_client()
        response = client.auth.sign_up(
            {
                "email": normalized_email,
                "password": password,
                "options": {
                    "data": {
                        "name": normalized_name,
                    }
                },
            }
        )
        pending_record = ensure_pending_user_record_by_email(
            client,
            normalized_email,
            normalized_name,
        )
        if not pending_record:
            st.session_state.auth_feedback = {
                "type": "warning",
                "message": (
                    "Conta criada, mas não foi possível concluir o registro "
                    "de aprovação automaticamente. Faça login para tentar "
                    "novamente ou contate o administrador."
                ),
            }
            _log_auth(
                logging.WARNING,
                "signup.pending_record_missing",
                user_email=_mask_email(normalized_email),
            )
            return True

        _log_auth(
            logging.INFO,
            "signup.success",
            user_email=_mask_email(normalized_email),
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
        error_msg = str(e).lower()
        LOGGER.exception("Falha no cadastro com email e senha")
        _log_auth(logging.ERROR, "signup.error", user_email=_mask_email(email), error=str(e))
        if "rate limit" in error_msg or "too many requests" in error_msg:
            st.session_state.auth_feedback = {
                "type": "warning",
                "message": (
                    "Você excedeu o limite de criação de contas ou envio de "
                    "emails deste serviço. Por favor aguarde um momento antes "
                    "de tentar novamente."
                ),
            }
        else:
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
    user_name = None
    user_metadata = getattr(user, "user_metadata", None)
    if isinstance(user_metadata, dict):
        user_name = user_metadata.get("name")

    return ensure_pending_user_record_by_email(
        client,
        getattr(user, "email", None),
        user_name,
    )


def ensure_pending_user_record_by_email(
    client: Client,
    email: Optional[str],
    name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Garante o registro pendente na authorized_users para o email informado."""
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        _log_auth(
            logging.WARNING,
            "authorization.ensure_pending.invalid_email",
        )
        return None

    normalized_name = (name or "").strip() or None

    try:
        response = (
            client.table("authorized_users")
            .select("id, approved")
            .eq("email", normalized_email)
            .execute()
        )
        existing_record = response.data[0] if response.data else None
        if existing_record:
            _log_auth(
                logging.INFO,
                "authorization.ensure_pending.already_exists",
                user_email=_mask_email(normalized_email),
                approved=existing_record.get("approved", False),
            )
            return existing_record

        client.table("authorized_users").insert({
            "email": normalized_email,
            "name": normalized_name,
            "approved": False,
        }).execute()
        _log_auth(
            logging.INFO,
            "authorization.ensure_pending.inserted",
            user_email=_mask_email(normalized_email),
        )

        response = (
            client.table("authorized_users")
            .select("id, approved")
            .eq("email", normalized_email)
            .execute()
        )
        ensured_record = response.data[0] if response.data else None
        _log_auth(
            logging.INFO,
            "authorization.ensure_pending.recheck",
            user_email=_mask_email(normalized_email),
            found=bool(ensured_record),
        )
        return ensured_record
    except Exception as e:
        LOGGER.exception("Erro ao registrar usuário pendente")
        _log_auth(
            logging.ERROR,
            "authorization.ensure_pending.error",
            user_email=_mask_email(normalized_email),
            error=str(e),
        )
        return None


def logout(should_rerun: bool = True):
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
        st.session_state.auth_tokens_from_query = None
        st.session_state._supabase_auth_storage = {}
        for key in (AUTH_QUERY_ACCESS_TOKEN_KEY, AUTH_QUERY_REFRESH_TOKEN_KEY):
            if key in st.query_params:
                del st.query_params[key]
        _clear_session_tokens_from_local_storage()
        _log_auth(logging.INFO, "logout.done")
        if should_rerun:
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

        .login-inline-link {
            margin-top: 8px;
            font-size: 13px;
            text-align: left;
        }

        .login-inline-link a {
            color: #0067ff;
            text-decoration: none;
            font-weight: 700;
        }

        .login-inline-link a:hover {
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
    _hydrate_recovery_tokens_from_hash()
    _capture_recovery_tokens_from_query()
    _capture_auth_tokens_from_query()
    _restore_session_from_local_storage_tokens()
    _hydrate_auth_tokens_from_local_storage()

    requested_mode = st.query_params.get("auth_mode")
    if isinstance(requested_mode, list):
        requested_mode = requested_mode[-1] if requested_mode else None
    if requested_mode in {"signin", "signup", "reset"}:
        st.session_state.auth_mode = requested_mode
        if "auth_mode" in st.query_params:
            del st.query_params["auth_mode"]
        st.rerun()

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

                if st.session_state.get("recovery_tokens"):
                    st.markdown(
                        "<p class='login-tab-caption'>Defina sua nova senha para concluir "
                        "a recuperação de acesso.</p>",
                        unsafe_allow_html=True,
                    )
                    with st.form("password_reset_form", clear_on_submit=False):
                        new_password = st.text_input(
                            "Nova senha",
                            type="password",
                            key="recovery_new_password",
                            placeholder="Digite sua nova senha",
                        )
                        confirm_new_password = st.text_input(
                            "Confirmar nova senha",
                            type="password",
                            key="recovery_confirm_password",
                            placeholder="Repita a nova senha",
                        )
                        reset_submit = st.form_submit_button(
                            "Atualizar senha",
                            type="primary",
                            use_container_width=True,
                        )

                    if reset_submit:
                        complete_password_reset(new_password, confirm_new_password)

                    render_html_block(
                        "<div class='login-switch-row'>Lembrou sua senha?"
                        " <a href='?auth_mode=signin' target='_self'>Voltar ao login</a>"
                        "</div>"
                    )

                elif auth_mode == "reset":
                    st.markdown(
                        "<p class='login-tab-caption'>Informe seu email para receber "
                        "o link de recuperação de senha.</p>",
                        unsafe_allow_html=True,
                    )
                    with st.form("reset_form", clear_on_submit=False):
                        reset_email = st.text_input(
                            "Email",
                            key="reset_email",
                            placeholder="voce@empresa.com",
                        )
                        reset_submit = st.form_submit_button(
                            "Enviar link de recuperação",
                            type="primary",
                            use_container_width=True,
                        )

                    if reset_submit:
                        if request_password_reset(reset_email):
                            st.session_state.auth_mode = "signin"
                            st.rerun()

                    render_html_block(
                        "<div class='login-switch-row'>Lembrou sua senha?"
                        " <a href='?auth_mode=signin' target='_self'>Voltar ao login</a>"
                        "</div>"
                    )

                elif auth_mode == "signin" or not is_signup_mode:
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
                        "<div class='login-inline-link'>"
                        "<a href='?auth_mode=reset' target='_self'>"
                        "Esqueci minha senha"
                        "</a></div>"
                    )

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
                # Reforça tokens na URL também nas subpáginas, evitando novo login no refresh.
                if st.session_state.get("session"):
                    _persist_session_tokens_in_query_params(st.session_state.session)

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
                kwargs={"should_rerun": False},
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
