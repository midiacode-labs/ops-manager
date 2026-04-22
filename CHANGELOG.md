# Changelog

Todas as mudanças relevantes deste projeto serão documentadas neste arquivo.

O formato segue o padrão [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

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
