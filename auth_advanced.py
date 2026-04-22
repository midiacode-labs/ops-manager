"""
Extensão do módulo auth.py para controle de acesso baseado em whitelist

COMO USAR:
1. Descomente as linhas abaixo no auth.py
2. Configure ALLOWED_EMAILS com os emails autorizados
3. Substitua a função display_auth_ui() pela versão com controle de acesso
"""

# ============================================================================
# OPÇÃO 1: Whitelist Simples de Emails
# ============================================================================

ALLOWED_EMAILS = [
    "lgavinho@midiacode.com",
    "user2@midiacode.com",
    "user3@midiacode.com",
]

def display_auth_ui_with_whitelist():
    """
    Versão de display_auth_ui() com controle de acesso por whitelist
    """
    import streamlit as st
    from auth import (
        initialize_auth_session,
        handle_auth_callback,
        check_session,
        get_current_user,
        get_google_oauth_url,
        logout,
    )
    
    initialize_auth_session()
    handle_auth_callback()
    
    if not check_session():
        st.warning("⚠️ Você precisa fazer login para acessar este aplicativo")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("### 🔐 Login com Google")
            
            if st.button("🔗 Fazer Login com Google", use_container_width=True, key="google_login"):
                oauth_url = get_google_oauth_url()
                if oauth_url:
                    st.markdown(f"[Clique aqui para fazer login]({oauth_url})")
                else:
                    st.error("Erro ao gerar URL de login. Verifique as configurações.")
        
        st.stop()
    
    else:
        user = get_current_user()
        
        # Verificar se o email está na whitelist
        if user and user.email not in ALLOWED_EMAILS:
            st.error(
                f"❌ Acesso Negado\n\n"
                f"Seu email ({user.email}) não está autorizado a acessar este aplicativo.\n\n"
                f"Se você deveria ter acesso, entre em contato com o administrador."
            )
            
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                if st.button("🚪 Logout", key="logout_unauthorized"):
                    logout()
            
            st.stop()
        
        # Usuário autenticado e autorizado
        if user:
            col1, col2, col3 = st.columns([2, 1, 0.5])
            
            with col1:
                st.success(f"✅ Bem-vindo, {user.user_metadata.get('name', user.email)}!")
            
            with col3:
                if st.button("🚪 Logout", key="logout_btn"):
                    logout()


# ============================================================================
# OPÇÃO 2: Controle de Acesso via Tabela no Supabase
# ============================================================================

def display_auth_ui_with_database_check():
    """
    Versão com controle de acesso baseado em tabela do Supabase
    
    SETUP:
    1. Criar tabela 'authorized_users' no Supabase:
       - email (TEXT, PRIMARY KEY)
       - name (TEXT, NULLABLE)
       - approved (BOOLEAN, DEFAULT true)
       - created_at (TIMESTAMP, DEFAULT now())
       - last_login (TIMESTAMP)
    
    2. Ativar RLS na tabela:
       - SELECT: usuários autenticados podem ver apenas seu próprio registro
    
    3. Inserir emails autorizados na tabela
    """
    import streamlit as st
    from auth import (
        initialize_auth_session,
        handle_auth_callback,
        check_session,
        get_current_user,
        get_supabase_client,
        get_google_oauth_url,
        logout,
    )
    from datetime import datetime
    
    initialize_auth_session()
    handle_auth_callback()
    
    if not check_session():
        st.warning("⚠️ Você precisa fazer login para acessar este aplicativo")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("### 🔐 Login com Google")
            
            if st.button("🔗 Fazer Login com Google", use_container_width=True, key="google_login"):
                oauth_url = get_google_oauth_url()
                if oauth_url:
                    st.markdown(f"[Clique aqui para fazer login]({oauth_url})")
                else:
                    st.error("Erro ao gerar URL de login. Verifique as configurações.")
        
        st.stop()
    
    else:
        user = get_current_user()
        
        if user:
            try:
                client = get_supabase_client()
                
                # Verificar se o usuário está autorizado
                response = client.table("authorized_users").select("approved").eq(
                    "email", user.email
                ).single().execute()
                
                authorized_record = response.data if response.data else None
                
                # Usuário não encontrado na tabela
                if not authorized_record:
                    st.error(
                        f"❌ Acesso Negado\n\n"
                        f"Seu email ({user.email}) não está registrado no sistema.\n\n"
                        f"Entre em contato com o administrador para solicitar acesso."
                    )
                    
                    col1, col2, col3 = st.columns([1, 1, 1])
                    with col2:
                        if st.button("🚪 Logout", key="logout_unauthorized"):
                            logout()
                    
                    st.stop()
                
                # Usuário não aprovado
                if not authorized_record.get("approved", False):
                    st.warning(
                        f"⏳ Acesso Pendente\n\n"
                        f"Seu email ({user.email}) está registrado, mas ainda não foi aprovado.\n\n"
                        f"Você será notificado quando seu acesso for liberado."
                    )
                    
                    col1, col2, col3 = st.columns([1, 1, 1])
                    with col2:
                        if st.button("🚪 Logout", key="logout_pending"):
                            logout()
                    
                    st.stop()
                
                # Atualizar last_login
                client.table("authorized_users").update({
                    "last_login": datetime.utcnow().isoformat()
                }).eq("email", user.email).execute()
                
                # Usuário autorizado e aprovado
                col1, col2, col3 = st.columns([2, 1, 0.5])
                
                with col1:
                    st.success(f"✅ Bem-vindo, {user.user_metadata.get('name', user.email)}!")
                
                with col3:
                    if st.button("🚪 Logout", key="logout_btn"):
                        logout()
                
            except Exception as e:
                st.error(f"Erro ao verificar autorização: {str(e)}")
                col1, col2, col3 = st.columns([1, 1, 1])
                with col2:
                    if st.button("🚪 Logout", key="logout_error"):
                        logout()


# ============================================================================
# SQL para criar tabela de usuários autorizados
# ============================================================================

"""
-- Execute isso no Supabase SQL Editor para criar a tabela

CREATE TABLE authorized_users (
    email TEXT PRIMARY KEY,
    name TEXT,
    approved BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    notes TEXT
);

-- Habilitar RLS
ALTER TABLE authorized_users ENABLE ROW LEVEL SECURITY;

-- Policy: usuários autenticados podem ver apenas seu próprio registro
CREATE POLICY "Users can view own record"
ON authorized_users
FOR SELECT
USING (auth.jwt() ->> 'email' = email);

-- Inserir usuários autorizados
INSERT INTO authorized_users (email, name, approved) VALUES
    ('lgavinho@midiacode.com', 'Luiz Gustavo', true),
    ('user2@midiacode.com', 'User 2', true),
    ('user3@midiacode.com', 'User 3', false);  -- Aprovação pendente

"""

