# Roadmap e estado

Legenda: ✅ implementado e testado · 🟡 implementado, verificação parcial · ⏳ pendente

## Fases 1–8

| Área | Estado | Notas |
|---|---|---|
| Fundações (config, SQLite/WAL, Alembic, logs JSON, erros, token, Host/CORS) | ✅ | |
| Identidade visual, layout, sidebar recolhível, barra superior, núcleo com estados reais | ✅ | verificado por capturas 1280×800 e 900×640 |
| Command Palette (⌘K) e barra de comando local (⌘J) | ✅ | comandos determinísticos, sem IA |
| Dashboard com dados reais e estado vazio | ✅ | |
| Projectos (CRUD, estados, marcos, links, histórico, progresso documentado, parados/bloqueados) | ✅ | |
| Tarefas (lista, Kanban com arrastar + teclado, subtarefas, dependências, bloqueios, filtros, foco) | ✅ | |
| Checklists e 7 modelos editáveis; projecto a partir de modelo | ✅ | |
| Notas Markdown (autosave, revisões, conflitos, rascunho local, arquivo) | ✅ | |
| Pesquisa global FTS5 (+ alternativa LIKE) | ✅ | |
| Agenda dia/semana, eventos, blocos de trabalho | ✅ | local; sem calendários externos |
| Revisão diária e planeamento semanal com dados reais | ✅ | |
| Base de conhecimento (lista + grafo React Flow, relações explícitas) | ✅ | |
| Motor de automações (gatilhos, condições, versões, histórico, limites, idempotência, cancelamento) | ✅ | |
| Construtor visual de automações (React Flow) | ✅ | fluxos lineares (sequenciais) |
| Notificações internas e lembretes | ✅ | |
| Notificações nativas macOS | 🟡 | plugin compilado na app; envio real ainda não observado (activar em Definições) |
| Métricas (períodos, tendências, por projecto, foco, automações, tabela alternativa) | ✅ | |
| Cofre (macOS Keychain) | ✅ | Keychain real detectado; gravação real só validada com backend de testes |
| Backups (manual, automático, verificação, teste de restauro, restauro, importação, exportação JSON) | ✅ | |
| Definições e diagnóstico (logs redigidos) | ✅ | |
| Integração GitHub (ligação, metadados, commits, PRs — só leitura) | 🟡 | testada com respostas simuladas; falta teste com token real |
| Assistente de IA (Anthropic, ferramentas tipadas, confirmação) | 🟡 | testado com fornecedor simulado; requer chave para teste real |
| Backend empacotado (PyInstaller onedir) | ✅ | 39 MB, arranque ≈ 3 s |
| Janela Tauri, .app, .dmg | ✅ | `.app` 90 MB, `.dmg` 51 MB (x86_64); arranque do backend 17 s no 1.º arranque; encerramento sem processos órfãos |

## Evolução: assistente holográfico e controlado por voz (Etapas A–G)

| Área | Estado | Notas |
|---|---|---|
| Cards holográficos com dados reais (10 áreas) e núcleo central | ✅ | `components/holo.tsx`, `pages/Dashboard.tsx` |
| Núcleo com 10 estados reais + indicador textual | ✅ | estados vindos do serviço de voz por SSE |
| Ferramentas tipadas com níveis de risco e confirmações | ✅ | `assistant/tools.py`, `actions.py` |
| Interpretação local em português (sem IA) | ✅ | `assistant/intents.py` |
| Relatórios (dia, semana, projectos, próximos passos, automações, problemas) | ✅ | factos / cálculos / recomendações / indisponível |
| Conversa: seguimento, contexto, repetir, cancelar, histórico com retenção | ✅ | |
| Palavra de activação «UAJI» (local) | 🟡 | validada com vozes sintéticas; falta validar com a voz real e ruído ambiente |
| Reconhecimento de fala local (Vosk) | 🟡 | validado com fala sintetizada; falta a sua pronúncia ao microfone |
| Síntese de fala, vozes do sistema, interromper/retomar | ✅ | sem voz pt-PT masculina nem pt-AO instaladas |
| Voz e personalidade (voz, velocidade, volume, idioma, tratamento) | ✅ | |
| Permissão do microfone na app instalada | 🟡 | `NSMicrophoneUsageDescription` incluído; pedido real do macOS ainda não observado |

## Autonomia, actividade e personalização

| Área | Estado | Notas |
|---|---|---|
| Iniciativa do assistente (10 regras, ofertas «sim/não», limites) | ✅ | entregue sozinho na app real; resposta por voz a validar com microfone |
| Monitor de actividade (app activa, inactividade, VS Code, Git) | ✅ | opt-in; testado com a sonda real deste Mac |
| Padrões e personalização (relatórios, bom-dia, contexto da IA) | 🟡 | precisa de ≥ 3 dias de dados reais |
| Acções no sistema (apps, sites, pastas, volume, estado, terminal) | ✅ | testadas com execução simulada; terminal desligado por omissão |
| Temas, destaque, densidade, escala, barra lateral | ✅ | |
| Painel personalizável e disposição adaptativa | ✅ | |

## Automação, desempenho, desenvolvimento e modelos próprios

| Área | Estado | Notas |
|---|---|---|
| Nós de Condição e Resultado no editor; acções «falar», «webhook» e «executar outro fluxo» | ✅ | fluxos sequenciais, sem ramos paralelos |
| Gatilhos webhook, GitHub e abrir aplicação | ✅ | GitHub testado com respostas simuladas |
| Centro de desempenho e objectivos | ✅ | tempo de ciclo só existe para tarefas iniciadas depois da migração 0005 |
| Referências UJ-n, repositórios locais e versões | ✅ | testado com repositórios Git reais |
| Branches, issues e releases do GitHub | 🟡 | falta token real |
| Command Palette: ficheiros, fluxos, comandos e assistente | ✅ | |
| Modelo próprio compatível com OpenAI | 🟡 | testado com servidor simulado; falta um modelo real |

## Próximos passos

1. Validar a voz com o microfone real: gravar amostras de «UAJI», medir falsas activações e a transcrição da sua pronúncia (ver docs/VOICE.md → «Como testar manualmente»).
2. Testar GitHub com um token *fine-grained* real e o assistente com uma chave real.
3. «Mostrar backups no Finder» a partir da app desktop (o download por blob pode não funcionar no WKWebView).
4. Edição de checklists com reordenação por arrastar.
5. Exportação de relatórios de actividade (Markdown/PDF).
6. Adaptador para modelos locais (ex.: servidor local compatível) implementando `Provider`.
7. Sincronização de issues GitHub ↔ tarefas (só após validar permissões e conflitos).
8. Assinatura e notarização da aplicação (requer conta Apple Developer).

## Decisões de identidade visual pendentes

A identidade usa um padrão geométrico de losangos genérico e acentos âmbar/dourado. **Não** foram usados símbolos culturais angolanos específicos (ex.: Sona/Lusona, padrões Chokwe) nem termos linguísticos sem confirmação. Se quiser incorporá-los, indique as referências que considera correctas.
