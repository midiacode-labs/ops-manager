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

## Executando a aplicação

Para iniciar o aplicativo Streamlit, use:

```bash
poetry run streamlit run app.py
```

O aplicativo ficará disponível em `http://localhost:8501`.

## Notificações no Slack

O projeto pode enviar uma notificação para o canal `#deploy` sempre que o ambiente for iniciado ou parado. A integração foi feita via Incoming Webhook do Slack, mantendo o segredo fora do código.

### Variáveis de ambiente

Configure estas variáveis em um arquivo `.env` local ou no ambiente de execução:

```bash
SLACK_DEPLOY_WEBHOOK_URL=https://hooks.slack.com/services/SEU/WEBHOOK/AQUI
DEPLOY_ENVIRONMENT_NAME=development
SLACK_DEPLOY_APP_NAME=Midiacode Ops Manager
```

- `SLACK_DEPLOY_WEBHOOK_URL`: webhook do Slack para o canal `#deploy`
- `DEPLOY_ENVIRONMENT_NAME`: nome exibido na mensagem, por exemplo `development`, `staging` ou `prod`
- `SLACK_DEPLOY_APP_NAME`: nome do sistema que vai aparecer na notificação

Se `SLACK_DEPLOY_WEBHOOK_URL` nao estiver definida, o app continua funcionando normalmente e apenas deixa de enviar a notificacao.

### Como criar o webhook no Slack

1. Acesse `https://api.slack.com/apps` e clique em `Create New App`.
2. Escolha `From scratch`, defina um nome como `Midiacode Deploy Notifications` e selecione o workspace da Midiacode.
3. No menu da app, entre em `Incoming Webhooks` e ative a opcao `Activate Incoming Webhooks`.
4. Clique em `Add New Webhook to Workspace`.
5. Escolha o canal `#deploy` e autorize a instalacao.
6. Copie a URL gerada e grave em `SLACK_DEPLOY_WEBHOOK_URL`.

### Exemplo de `.env`

```bash
SLACK_DEPLOY_WEBHOOK_URL=https://hooks.slack.com/services/SEU/WEBHOOK/AQUI
DEPLOY_ENVIRONMENT_NAME=development
SLACK_DEPLOY_APP_NAME=Midiacode Ops Manager
```

### Testar so a notificacao via linha de comando

Depois de configurar o `.env`, voce pode testar apenas o envio para o Slack sem abrir o Streamlit:

```bash
poetry run python slack_notifications.py
```

Voce tambem pode customizar os dados do teste:

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
