# Modelo de dados

SQLite com `PRAGMA foreign_keys=ON` e WAL. Identificadores UUID4 em texto. Todas as datas/horas guardadas em **UTC** e devolvidas com fuso (`UTCDateTime`); a API recusa datas sem fuso. Dias locais (agenda, revisões, métricas) usam o fuso definido nas Definições (por omissão `Africa/Luanda`). Migrações em `backend/alembic/versions` (0001 esquema, 0002 índice de pesquisa).

## Entidades

| Tabela | Descrição | Relações / regras |
|---|---|---|
| `projects` | Nome, descrição, categoria, estado (planned/active/paused/blocked/done/archived), prioridade, datas, objectivos, resultados esperados, motivo de bloqueio, `archived_at` | Bloqueado exige motivo. Fim ≥ início. |
| `milestones` | Marcos de um projecto | `project_id` **CASCADE** |
| `project_links` | Repositórios GitHub e outros links | `project_id` **CASCADE**; URLs http(s) validados |
| `tasks` | Título, descrição, estado (todo/in_progress/blocked/done), prioridade, prazo, estimativa, critérios de conclusão, bloqueio, `completed_at`, `archived_at`, `postponed_count` | `project_id` **SET NULL**; `parent_id` (subtarefas, 1 nível) **CASCADE** |
| `task_dependencies` | Tarefa depende de outra | ambos **CASCADE**; ciclos recusados; não se conclui com dependências abertas |
| `focus_sessions` | Sessões de foco (cronómetro ou registo manual) | `task_id`/`project_id` **SET NULL**; só uma sessão activa |
| `checklists` | Checklists e **modelos** (`is_template`); `builtin_key` para os 7 modelos incluídos | `project_id`/`task_id` **CASCADE**; `source_template_id` **SET NULL** |
| `checklist_items` | Itens com secção, ordem e estado | **CASCADE** |
| `notes` | Markdown, tipo (nota, decisão, ideia, conceito, solução, erro, documentação, referência, lição), `in_knowledge_base`, etiquetas, `revision` | `project_id`/`task_id` **SET NULL** |
| `note_revisions` | Histórico de conteúdo (máx. 50 por nota; gravações a <10 min agrupadas) | **CASCADE** |
| `relations` | Relação explícita entre quaisquer duas entidades (`source_type/id` → `target_type/id`, rótulo) | removidas quando uma das partes é eliminada (pelo serviço) |
| `events` | Eventos e blocos de trabalho (início/fim com fuso) | `project_id`/`task_id` **SET NULL**; fim > início |
| `reviews` | Revisões diárias/semanais (objectivos, conquistas, bloqueios, reflexão, plano) | único por (`kind`, `period_start`) |
| `automations` | Nome, estado, versão actual, tipo de gatilho, última/próxima execução | — |
| `automation_versions` | Definição JSON de cada versão (imutável) | **CASCADE**; único (`automation_id`, `version`) |
| `automation_runs` | Execuções: gatilho, estado, erro, duração, contexto, `idempotency_key` **única** | **CASCADE** |
| `automation_run_steps` | Registo de cada etapa (entrada, saída, erro, tentativas) | **CASCADE** |
| `notifications` | Internas; `dedupe_key` única evita repetições; `native_sent` para o macOS | apagadas 90 dias após lidas |
| `integrations` | Estado e configuração **não secreta** por fornecedor | `secret_id` **SET NULL** |
| `secrets` | **Apenas metadados** (nome, serviço, últimos 4 caracteres). O valor está no Keychain com a conta = `id` | — |
| `backups` | Ficheiro, tipo, tamanho, SHA-256, revisão do esquema, estado de verificação | sincronizada com os ficheiros em disco após restauro |
| `activity` | Histórico de alterações; `sensitive` marca acções do cofre (excluídas do dashboard) | — |
| `settings` | Pares chave/valor JSON (mesclados com valores por omissão) | — |
| `search_index` | Tabela virtual **FTS5** (`unicode61 remove_diacritics`), mantida pelos serviços; alternativa com `LIKE` se o SQLite não tiver FTS5 | — |

## Regras de eliminação e arquivo

- **Arquivar** é a operação por omissão (projectos, tarefas, notas): os dados permanecem no histórico e nas métricas.
- **Eliminar** exige `?confirm=true` (HTTP 428 sem confirmação) e é registado no histórico.
- Eliminar um projecto **não** elimina as tarefas e notas: ficam sem projecto (`SET NULL`).

## Regra de progresso dos projectos

`progresso = tarefas de topo concluídas ÷ tarefas de topo não arquivadas`. Subtarefas não contam (são detalhe da tarefa-mãe, que só pode ser concluída com as subtarefas fechadas). Sem tarefas → progresso **indefinido** (não 0 %). Marcos são mostrados à parte. Um projecto activo sem actividade há 14 dias é sinalizado.

## Persistência e migrações

- Base nova: `alembic upgrade head` no arranque.
- Base existente com migração pendente: **backup automático `pre_migration`** antes de migrar.
- Os modelos incluídos são criados apenas se o seu `builtin_key` não existir (edições do utilizador nunca são sobrescritas).

## Objectivos, versões e código (migração 0005)

- `goals`: objectivo mensurável, opcionalmente de um projecto; ao eliminar o projecto, o objectivo fica sem projecto. Progresso = tarefas concluídas ÷ tarefas ligadas.
- `project_versions`: versão de um projecto (nome único por projecto, tag Git, estado). É eliminada com o projecto.
- `code_links`: commit, PR, branch ou issue ligado a uma tarefa (único por tarefa, tipo, repositório e referência). É eliminado com a tarefa.
- `tasks`: novos campos `number` (referência UJ-n), `started_at`, `blocked_at`, `blocked_seconds`, `goal_id` e `version_id`.
- `automations`: `webhook_secret_hash` e `trigger_state` (ex.: eventos GitHub já vistos).
- `activity_sessions` (migração 0004) e `assistant_messages` (migração 0003) estão documentadas em AUTONOMY.md e VOICE.md.
