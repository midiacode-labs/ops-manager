-- ============================================================================
-- Criar tabela authorized_users para gerenciar autorizações
-- ============================================================================
-- EXECUTE ISSO NO SUPABASE SQL EDITOR (Database > SQL Editor)

-- 1. Criar tabela
CREATE TABLE IF NOT EXISTS authorized_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    approved BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    approved_by TEXT,
    approved_at TIMESTAMP,
    notes TEXT
);

-- 2. Criar índices para melhorar performance
CREATE INDEX IF NOT EXISTS idx_authorized_users_email ON authorized_users(email);
CREATE INDEX IF NOT EXISTS idx_authorized_users_approved ON authorized_users(approved);

-- 3. Habilitar Row Level Security (RLS)
ALTER TABLE authorized_users ENABLE ROW LEVEL SECURITY;

-- 4. Criar policy: usuários autenticados podem ver todos os registros
-- (importante para admin gerir usuários)
CREATE POLICY "Enable read for authenticated users"
ON authorized_users FOR SELECT
USING (auth.role() = 'authenticated');

-- 5. Criar policy: apenas usuários aprovados com role 'admin' podem atualizar
CREATE POLICY "Enable update for admin users"
ON authorized_users FOR UPDATE
USING (
    auth.role() = 'authenticated' AND
    EXISTS (
        SELECT 1 FROM authorized_users
        WHERE email = auth.jwt() ->> 'email'
        AND approved = true
    )
)
WITH CHECK (
    auth.role() = 'authenticated' AND
    EXISTS (
        SELECT 1 FROM authorized_users
        WHERE email = auth.jwt() ->> 'email'
        AND approved = true
    )
);

-- 6. Criar policy: apenas usuários aprovados podem fazer insert
CREATE POLICY "Enable insert for authenticated users"
ON authorized_users FOR INSERT
WITH CHECK (auth.role() = 'authenticated');

-- 7. Garantir registro automático de novos usuários do Auth como pendentes
-- Função em schema privado para evitar SECURITY DEFINER em schema exposto.
CREATE SCHEMA IF NOT EXISTS private;

CREATE OR REPLACE FUNCTION private.handle_new_auth_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF NEW.email IS NULL OR btrim(NEW.email) = '' THEN
        RETURN NEW;
    END IF;

    INSERT INTO public.authorized_users (email, name, approved)
    VALUES (
        lower(NEW.email),
        NULLIF(NEW.raw_user_meta_data ->> 'name', ''),
        false
    )
    ON CONFLICT (email) DO NOTHING;

    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION private.handle_new_auth_user() FROM PUBLIC;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
AFTER INSERT ON auth.users
FOR EACH ROW
EXECUTE FUNCTION private.handle_new_auth_user();

-- ============================================================================
-- Inserir usuários iniciais (OPCIONAL - modifique conforme necessário)
-- ============================================================================

INSERT INTO authorized_users (email, name, approved, approved_by, approved_at)
VALUES 
    ('lgavinho@midiacode.com', 'Luiz Gustavo', true, 'admin', NOW())
ON CONFLICT (email) DO NOTHING;

-- ============================================================================
-- Função auxiliar para atualizar last_login automaticamente
-- ============================================================================

CREATE OR REPLACE FUNCTION update_last_login()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_login = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Criar trigger
DROP TRIGGER IF EXISTS trigger_update_last_login ON authorized_users;
CREATE TRIGGER trigger_update_last_login
BEFORE UPDATE ON authorized_users
FOR EACH ROW
WHEN (OLD.approved IS DISTINCT FROM NEW.approved)
EXECUTE FUNCTION update_last_login();

-- ============================================================================
-- Verificar se tabela foi criada com sucesso
-- ============================================================================

SELECT * FROM authorized_users;

