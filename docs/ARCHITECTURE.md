# Arquitectura

```
┌───────────────────────── Tauri 2 (Rust) ─────────────────────────┐
│ • escolhe porta livre em 127.0.0.1 e gera token aleatório         │
│ • lança o backend (venv em dev; executável PyInstaller em prod)   │
│ • comando `backend_config` → { baseUrl, token }                   │
│ • termina o backend ao sair (e o backend vigia o processo pai)    │
│ ┌──────────── WebView (React) ────────────┐                       │
│ │ fetch http://127.0.0.1:<porta>/api/...  │──HTTP + Bearer token──┼──► FastAPI (Python)
│ └─────────────────────────────────────────┘                       │      │
└───────────────────────────────────────────────────────────────────┘      ├─ SQLite (WAL, FTS5)
                                                                           ├─ macOS Keychain
                                                                           └─ backups/*.zip, logs/
```

Em desenvolvimento no browser, o Vite (porta 1420) faz proxy de `/api` para o backend e injecta o token.

## Backend (`backend/uanji`)

| Módulo | Responsabilidade |
|---|---|
| `config.py` | Configuração por ambiente (`UANJI_*`). |
| `db.py` | Motor SQLite (WAL, `foreign_keys=ON`, `busy_timeout`), sessões, utilitários Alembic. |
| `models.py` | Modelo de dados SQLAlchemy 2 (ver DATA_MODEL.md). |
| `schemas.py` | Contratos Pydantic de entrada/saída (OpenAPI em `/docs`). |
| `errors.py` | Erros de domínio e formato único `{"error": {code, message, details}}`. |
| `logging_setup.py` | Logs JSON por linha, rotativos, com redacção de tokens. |
| `events.py` | Barramento de eventos entregues **após commit** (ex.: `task.completed`). |
| `services/` | Regras de negócio: projectos, tarefas, checklists/modelos, notas/conhecimento, agenda/revisões, métricas, notificações, cofre, backups, comandos locais. |
| `automation/` | Catálogo de acções tipadas e motor (validação, versões, execução, agendamento). |
| `integrations/` | Contrato `IntegrationAdapter` + adaptador GitHub (leitura). |
| `assistant/` | Abstracção de fornecedores de IA + ferramentas internas tipadas. |
| `api/` | Routers FastAPI finos (validação → serviço → schema). |
| `main.py` | Criação da app, middlewares, agendador, arranque/encerramento. |

Princípios: os routers não contêm regras de negócio; cada pedido corre numa transacção que é confirmada **antes** da resposta (`Depends(get_db, scope="function")`); operações multi-entidade (ex.: projecto a partir de modelo) correm numa única transacção.

### Agendador

Ciclo de 60 s em segundo plano (thread): automações programadas e de prazo, lembretes (prazos, atrasos, revisões), backups automáticos e limpeza de notificações antigas. Sem polling agressivo; tudo idempotente.

### Motor de automações

- Definição versionada: `trigger` + `conditions` + `steps` (+ posições do construtor em `ui`).
- Gatilhos: manual, programado (intervalo ≥ 15 min, diário, uma vez), tarefa concluída, prazo próximo.
- Acções (apenas internas, tipadas): criar tarefa, actualizar estado de tarefa/projecto, criar nota, registar evento, gerar resumo local, notificar. **Não existe acção de shell, ficheiros ou código.**
- Execução sequencial; cada etapa é confirmada e registada (entrada, saída, erro, tentativas, duração).
- Falhas recuperáveis (BD ocupada) repetidas até 2 vezes; limite de 25 etapas e 30 s por execução; cancelamento entre etapas; encadeamento limitado a 3 níveis.
- `idempotency_key` única impede execuções duplicadas do mesmo evento.
- **Sem rollback automático**: se a etapa 3 falhar, as etapas 1–2 permanecem (indicado na interface).
- Parâmetros aceitam `{{caminho}}` — substituição de texto, nunca avaliação.

### Assistente e voz

Detalhe completo em [VOICE.md](VOICE.md). Em resumo:

- `assistant/conversation.py` é o ponto único de entrada (texto e voz): resolve respostas pendentes (parâmetros em falta, escolhas, «sim/não»), interpreta localmente (`intents.py`) e só recorre ao fornecedor de IA para o que não reconhece.
- `assistant/tools.py` define todas as operações permitidas (parâmetros Pydantic, nível de risco, descrição do que muda). Partilhado pelo modo local e pela IA. `actions.py` executa cada ferramenta numa transacção própria e regista a actividade.
- `assistant/reports.py` constrói relatórios só com registos existentes, separando factos, cálculos, recomendações e informação indisponível.
- `assistant/core.py`: `Provider` → `AnthropicProvider` (modelo por omissão `claude-opus-5-5`). Escritas propostas pela IA exigem sempre confirmação.
- `voice/`: captura (PortAudio), VAD, palavra de activação (MFCC + DTW), STT (Vosk), TTS (`say`) e `service.py` (máquina de estados + SSE em `/api/voice/events`).
- Histórico de conversa na tabela `assistant_messages` (migração 0003), com retenção configurável aplicada pelo agendador.

### Desempenho, código e modelos

- `services/performance.py`: centro de desempenho, sobre `started_at`, `blocked_at`, `blocked_seconds` das tarefas e a tabela `goals`.
- `services/devwork.py` e `api/devwork.py`: objectivos, versões (`project_versions`), ligações código ↔ tarefa (`code_links`, referências `UJ-n`), repositórios GitHub e pastas locais, e pesquisa de ficheiros da Command Palette. Migração 0005.
- `automation/engine.py`: condições por etapa (`conditions`, `on_false`), webhook (`/hooks/{id}`), verificação do GitHub de 5 em 5 minutos e gatilho de abertura de aplicação.
- `assistant/openai_compat.py`: `OpenAICompatibleProvider`. Para outro formato de API, basta implementar `Provider.turn` e registá-lo em `core._make_provider`.

## Frontend (`frontend/src`)

| Pasta | Conteúdo |
|---|---|
| `api/` | Cliente HTTP (descoberta do backend, erros tipados), tipos e hooks TanStack Query. |
| `components/` | UI base (botões, campos, painéis, diálogos nativos `<dialog>`), núcleo visual, gráficos, layout. |
| `features/` | Formulários (RHF + Zod), autosave, relações, revisão, lógica do construtor de automações. |
| `pages/` | Uma página por área; carregadas sob pedido (code-splitting). |
| `lib/` | Utilitários, toasts, estado do núcleo (Zustand). |

O **núcleo UANJI** (SVG + CSS, sem WebGL) reflecte estados reais. Os estados do assistente vêm do serviço de voz por SSE (`lib/voice.ts`, lido com `fetch` porque o `EventSource` não envia o cabeçalho `Authorization`): inactivo, à espera da palavra, a ouvir, a interpretar, a preparar, a falar, a executar, a aguardar confirmação, concluído, erro. *A processar* indica pedidos à API em curso. O painel inicial organiza as áreas em cards holográficos (`components/holo.tsx`) com dados reais; alertas e atrasos têm destaque visual.

## Desempenho em hardware antigo

Sem Three.js/WebGL; animações CSS limitadas e desactiváveis (`prefers-reduced-motion` + preferência própria); relógio actualizado ao minuto; refresco do dashboard a cada 60 s; listas paginadas no backend; grafo com `onlyRenderVisibleElements`; páginas lazy (bundle inicial ≈ 137 KB gzip); backend empacotado em modo *onedir* (arranque ≈ 3 s neste MacBook).
