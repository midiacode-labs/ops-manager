# Ops Manager

Um painel de gerenciamento de operações criado com Streamlit para supervisionar e controlar os aspectos operacionais do ecossistema Midiacode. 

## Requisitos

Este projeto foi configurado com Poetry e Python 3.11. As principais dependências são:

- streamlit==1.45.1
- pandas==2.2.3
- numpy==2.2.5
- matplotlib==3.10.3

## Instalação

1. Certifique-se de ter o Poetry instalado:
   ```bash
   # Para instalar o Poetry (caso ainda não tenha)
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. Clone o repositório e instale as dependências:
   ```bash
   cd ops-manager
   poetry install
   ```

## Configuração do `.env`

Crie um arquivo `.env` na raiz do projeto com as variáveis necessárias para o login com Supabase e, opcionalmente, para notificações no Slack:

```bash
SUPABASE_URL=https://<seu-project-ref>.supabase.co
SUPABASE_KEY=<sua-anon-key-ou-publishable-key>
STREAMLIT_REDIRECT_URL=http://localhost:8501

SLACK_DEPLOY_WEBHOOK_URL=https://hooks.slack.com/services/SEU/WEBHOOK/AQUI
DEPLOY_ENVIRONMENT_NAME=development
SLACK_DEPLOY_APP_NAME=Midiacode Ops Manager
```

### Variáveis obrigatórias para login

- `SUPABASE_URL`: URL do projeto no Supabase.
- `SUPABASE_KEY`: use a chave pública do projeto (`anon` ou `publishable`).
- `STREAMLIT_REDIRECT_URL`: URL base do app Streamlit que recebe o callback do login.

### Variáveis opcionais para Slack

- `SLACK_DEPLOY_WEBHOOK_URL`: webhook do Slack para o canal `#deploy`.
- `DEPLOY_ENVIRONMENT_NAME`: nome exibido na mensagem, por exemplo `development`, `staging` ou `prod`.
- `SLACK_DEPLOY_APP_NAME`: nome do sistema que vai aparecer na notificação.

Observações:

- Não use a `service_role` key no app.
- Se `SLACK_DEPLOY_WEBHOOK_URL` não estiver definida, o app continua funcionando normalmente e apenas deixa de enviar a notificação.

## Configuração do Login com Supabase

O fluxo de login deste projeto usa o Supabase Auth com Google OAuth.

### Quick start

1. Crie o arquivo `.env` na seção [Configuração do `.env`](#configuração-do-env).
2. Crie ou selecione um projeto no Supabase.
3. Habilite o provedor Google em `Authentication` -> `Providers` no Supabase.
4. Configure o cliente OAuth Web no Google Cloud Console com as URLs de callback do projeto.
5. Execute o SQL de `setup_authorized_users_table.sql` e insira pelo menos um usuário com `approved = true`.

Depois disso, inicie o app com `poetry run streamlit run app.py`.

### Dependências relevantes

Além do Streamlit, o login depende principalmente de:

- `supabase`
- `python-dotenv`

### 1. Criar e configurar o projeto no Supabase

1. Crie ou use um projeto existente no Supabase.
2. No dashboard do Supabase, vá em `Authentication` -> `Providers`.
3. Habilite o provedor `Google`.
4. Configure o `Client ID` e `Client Secret` do Google OAuth.

### 2. Configurar o Google OAuth

No Google Cloud Console, configure um cliente OAuth Web com estas URLs:

- Authorized JavaScript origins:
   - `http://localhost:8501`
   - `https://<seu-project-ref>.supabase.co`
- Authorized redirect URIs:
   - `http://localhost:8501`
   - `https://<seu-project-ref>.supabase.co/auth/v1/callback`

Observação: para produção, adicione também a URL pública do app no Streamlit Cloud.

### 3. Criar a tabela de autorização

O login autentica o usuário no Google, mas o acesso ao app só é liberado se o email estiver autorizado na tabela `authorized_users`.

Você deve criar essa tabela no Supabase executando o SQL do arquivo:

- `setup_authorized_users_table.sql`

Esse script cria:

- tabela `authorized_users`
- índices
- políticas RLS
- trigger de atualização de `last_login`

### 4. Aprovação de usuários

O fluxo implementado neste projeto funciona assim:

1. O usuário faz login com Google via Supabase.
2. O app consulta a tabela `authorized_users`.
3. Se o usuário não existir ou não estiver com `approved = true`, o acesso é bloqueado.
4. Apenas usuários aprovados acessam o dashboard principal.

### 5. Primeiro acesso administrativo

Garanta que pelo menos um usuário administrador esteja inserido manualmente na tabela `authorized_users` com `approved = true`, para conseguir acessar o app e aprovar outros usuários.

Exemplo:

```sql
insert into authorized_users (email, name, approved, approved_by, approved_at)
values ('seu-email@empresa.com', 'Seu Nome', true, 'system', now())
on conflict (email) do nothing;
```

## Executando a aplicação

Para iniciar o aplicativo Streamlit, use:

```bash
poetry run streamlit run app.py
```

O aplicativo ficará disponível em `http://localhost:8501`.

Se o login estiver configurado corretamente, ao abrir o app você verá a tela de login e poderá autenticar com Google via Supabase.

## Notificações no Slack

O projeto pode enviar uma notificação para o canal `#deploy` sempre que o ambiente for iniciado ou parado. A integração foi feita via Incoming Webhook do Slack, mantendo o segredo fora do código.

As variáveis de ambiente do Slack estão centralizadas na seção [Configuração do `.env`](#configuração-do-env).

### Como criar o webhook no Slack

1. Acesse `https://api.slack.com/apps` e clique em `Create New App`.
2. Escolha `From scratch`, defina um nome como `Midiacode Deploy Notifications` e selecione o workspace da Midiacode.
3. No menu da app, entre em `Incoming Webhooks` e ative a opção `Activate Incoming Webhooks`.
4. Clique em `Add New Webhook to Workspace`.
5. Escolha o canal `#deploy` e autorize a instalação.
6. Copie a URL gerada e grave em `SLACK_DEPLOY_WEBHOOK_URL`.

### Testar só a notificação via linha de comando

Depois de configurar o `.env`, você pode testar apenas o envio para o Slack sem abrir o Streamlit:

```bash
poetry run python slack_notifications.py
```

Você também pode customizar os dados do teste:

```bash
poetry run python slack_notifications.py \
   --action iniciado \
   --source cli-teste \
   --status-code 200 \
   --payload "Teste manual do webhook"
```

## Scripts CLI

### Parar Ambiente de Desenvolvimento

Para parar o ambiente de desenvolvimento via linha de comando:

```bash
python3 stop_dev_environment.py
```

Este script invoca uma função Lambda da AWS para parar o ambiente de desenvolvimento e fornece feedback sobre o status da operação.

## Estrutura do Projeto

- `app.py` - O arquivo principal da aplicação Streamlit
- `stop_dev_environment.py` - Script CLI para parar o ambiente de desenvolvimento
- `pyproject.toml` - Configurações do Poetry e dependências do projeto

## Desenvolvimento

Para adicionar novas dependências ao projeto:

```bash
poetry add nome-do-pacote
```

Para atualizar as dependências:

```bash
poetry update
```

Para atualizar o arquivo `requirements.txt` com as dependências principais, execute:

```bash
poetry export -f requirements.txt --without-hashes --output requirements.txt --only main
```
