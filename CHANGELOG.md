# Changelog

Todas as mudanças relevantes deste projeto serão documentadas neste arquivo.

O formato segue o padrão [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [0.4.0] - 2026-04-25

### Adicionado
- Suporte à coleta de evidências de backup do DynamoDB, incluindo metadados da tabela, backups contínuos e backups nativos via AWS CLI.
- Inclusão de recursos DynamoDB configuráveis por `DYNAMODB_RESOURCE_ARNS` no relatório consolidado e na página de backup.
- Utilitário `app_version.py` para leitura centralizada da versão da aplicação a partir do `pyproject.toml`.
- Exibição da versão atual da aplicação no dashboard principal e em páginas operacionais.
- Inclusão do pacote `awscli` em `packages.txt` e `requirements.txt` para suportar a coleta operacional de evidências.

### Alterado
- Página de backup aprimorada com parsing mais robusto de datas, detecção de backups desatualizados e alertas visuais para dados parciais ou antigos.
- Relatório PDF de evidências de backup expandido para refletir os novos campos e recursos monitorados.
- Fluxo de aprovação e revogação de usuários em `pages/manage_users.py` reforçado com validações de sessão, tratamento de erros e mensagens mais claras.
- Notificações do Slack ajustadas para detectar com mais precisão ações de início e parada do ambiente, evitando falso positivo na escolha do emoji.

### Documentação
- `README.md` atualizado com instruções de configuração e uso das evidências de backup para DynamoDB e dependências operacionais.

## [0.3.0] - 2026-04-22

### Adicionado
- Nova página de evidências de backup em `pages/backup.py`, com navegação dedicada na barra lateral.
- Geração de relatório em PDF para evidências de backup via `backup_pdf_report.py`.
- Coleta e consolidação de evidências de backup para OpenSearch e RDS, incluindo priorização de status de recursos.
- Registro automático de novos usuários autenticados como pendentes na tabela `authorized_users`.
- Script SQL de suporte para criação/ajuste da tabela de usuários autorizados em `setup_authorized_users_table.sql`.

### Alterado
- Fluxo de autenticação migrado para login e solicitação de acesso com e-mail e senha em `auth.py`.
- Remoção do fluxo de autenticação com Google OAuth e da lógica de fallback PKCE.
- Ajustes de interface e feedback no processo de autenticação (entrar, solicitar acesso e mensagens de estado).
- Títulos e elementos visuais da página de backup atualizados, incluindo indicador de status não suportado.

### Melhorado
- Coleta de evidências de backup do OpenSearch refatorada para uso de API com assinatura SigV4.
- Logging do fluxo de backup aprimorado para facilitar rastreabilidade e diagnóstico.

### Documentação
- `README.md` atualizado com orientações e contexto das novas funcionalidades de backup e autenticação.
- Arquivo de instruções de autenticação atualizado em `.github/instructions/auth.instructions.md`.

## [0.2.0] - 2026-04-22

### Adicionado
- Integração com Supabase para autenticação e autorização no fluxo da aplicação.
- Gerenciamento de registros de usuários pendentes diretamente no fluxo de autenticação.
- Logging estruturado para os fluxos de autenticação e gerenciamento de usuários.
- Notificações no Slack para ações de ambiente, com suporte a metadados de usuário.

### Alterado
- Atualização de dependências e ajustes de configuração do projeto para suportar o novo fluxo com Supabase.
- Melhorias de interface no dashboard, barra lateral, navegação e renderização de avatar.
- Ajuste de terminologia de ambiente para sandbox nas ações de operação.
- Integração da branch de autenticação no fluxo principal de desenvolvimento.

### Corrigido
- Correção da URL de health check do Midiacode Lite no dashboard.
- Correção da sintaxe de lambda na seleção de usuários em `pages/manage_users.py`.

### Refatorado
- Ajustes nas ações de notificação do Slack e melhoria na formatação das mensagens.

### Documentação
- Inclusão de detalhes de configuração no `README.md` e no exemplo de variáveis de ambiente `.env.example`.
- Atualização dos arquivos de instruções do projeto em `.github/instructions/`.
