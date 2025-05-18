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

## Estrutura do Projeto

- `app.py` - O arquivo principal da aplicação Streamlit
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
