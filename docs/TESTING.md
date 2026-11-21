# Testes

## Comandos

```bash
# Backend (107 testes)
cd backend
.venv/bin/pytest                   # testes
.venv/bin/ruff check uanji tests   # lint
.venv/bin/ruff format --check uanji tests
.venv/bin/mypy uanji               # tipos (strict)

# Frontend (48 testes)
cd frontend
npx vitest run                     # testes (jsdom)
npx tsc -b --noEmit                # tipos (strict)
npx vite build                     # build de produção
```

Neste MacBook Air 2015: backend ≈ 1 min, frontend ≈ 35 s, mypy ≈ 2 min.

Auto-teste do pipeline de voz com componentes reais (sem microfone): `cd backend && .venv/bin/python -m uanji.voice.selftest`.

## Cobertura por área

### Backend (`backend/tests`)

| Ficheiro | Cobre |
|---|---|
| `test_foundations.py` | Token obrigatório, protecção de Host, migração de BD nova até à última revisão, modelos semeados uma vez, formato de erros de validação e 404, OpenAPI |
| `test_projects_tasks.py` | CRUD, histórico, bloqueio com motivo, datas, eliminação com confirmação (tarefas desassociadas), regra de progresso, ciclo de vida das tarefas, subtarefas, dependências e ciclos, atrasos e filtros, recusa de datas sem fuso, adiamentos, foco, links e marcos |
| `test_content.py` | Autosave/revisões/conflito 409, restauro de revisões, grafo e relações, projecto a partir de modelo (transacção única), duplicação, pesquisa FTS5 (acentos, injecção de sintaxe, actualização e remoção do índice), comandos locais, agenda e revisões |
| `test_automations.py` | Validação (acções desconhecidas, parâmetros, intervalo mínimo), execução sequencial com modelos, falha sem rollback + notificação, condições, gatilho de conclusão idempotente, limite de encadeamento, agendamento e prazos, versões e reposição, automações inactivas, cancelamento, garantia de que `render` nunca avalia código |
| `test_security_data.py` | Segredos fora da BD/actividade/dashboard, redacção de logs, backup → verificação → restauro de teste → restauro com backup de segurança, rejeição de backups adulterados e nomes maliciosos, importação em duas fases, exportação sem segredos, GitHub com transporte simulado (ligação, 401, URL inválido), assistente sem fornecedor (503) e com fornecedor simulado (ferramentas, dados marcados como não confiáveis, confirmação obrigatória), definições validadas, diagnóstico sem segredos, deduplicação de lembretes, integridade referencial |
| `test_assistant_voice.py` | Interpretação local dos exemplos pedidos, criação real de tarefa por comando, relatórios só com dados reais (factos/cálculos/indisponível), projecto mais atrasado, confirmação de acções destrutivas por voz («sim»/«não»), política de confirmação configurável, ambiguidade e parâmetros em falta, contexto «este projecto», repetição, IA indisponível e escritas da IA sempre confirmadas, validação e persistência de voz/tratamento após reinício, retenção do histórico, microfone fechado com a escuta desligada, «UAJI» → pedido por voz → tarefa criada, botão do microfone (uso temporário), permissão negada, STT em falta, TTS indisponível, interromper e retomar a fala, catálogo só com vozes instaladas |
| `test_autonomy.py` | Monitor de actividade, padrões, regras de iniciativa e limites, acções no sistema com execução simulada, terminal sempre confirmado, aparência e utilização |
| `test_devwork.py` | Números UJ-n, tempo de ciclo e bloqueios, filtro por projecto, objectivos e versões, repositório Git real, GitHub simulado, condições nos fluxos, webhook, gatilhos GitHub e de aplicação, ficheiros da Command Palette, modelo próprio com servidor simulado |
| `test_integration_flow.py` | **Fluxo completo da secção 13**: projecto → tarefas → nota → concluir → métricas → pesquisa → automação → backup → restauro em BD de teste → reinício com persistência |

### Frontend (`frontend/src/__tests__`)

| Ficheiro | Cobre |
|---|---|
| `client.test.ts` | Token e JSON, erros com campos, 428, falha de rede |
| `dashboard.test.tsx` | Carregamento, estado vazio com acção, dados reais, erro com «Tentar novamente» |
| `forms.test.tsx` | Validação de título, motivo de bloqueio, criação com projecto e prazo ISO, erros de campo do backend |
| `navigation.test.tsx` | Barra lateral, Command Palette (⌘K) com resultados, barra de comando, aviso de backend offline |
| `graph.test.ts` | Ordem sequencial a partir do grafo; ramificações, nós soltos, ciclos, fluxo vazio |
| `assistant.test.tsx` | Núcleo com indicador textual em todos os estados, relatório estruturado e pedido de voz, acção destrutiva só após «Confirmar», privacidade/permissão negada/transcrição parcial, explicação antes da primeira utilização do microfone, dashboard holográfico com os 10 cards e estado de voz, vozes instaladas filtradas por tipo, tratamento guardado sem alterar a escuta |
| `autonomy.test.tsx` | Disposição do painel, temas, mensagens por iniciativa |
| `devwork.test.tsx` | Centro de desempenho, código ligado a tarefas, Command Palette, configuração do modelo próprio |
| `automation-editor.test.tsx` | Adicionar acção, validação no backend, gravação da definição; erros de validação; fluxo vazio recusado |

## Verificações manuais realizadas

- Execução do backend + frontend reais (`scripts/dev.sh`) e capturas a 1280×800 e 900×640 (Chrome headless): dashboard, projecto, Kanban, notas, automações, métricas.
- Executável PyInstaller: arranque com BD nova em 3,3 s, migrações, FTS5, Keychain real detectado, encerramento limpo.
- App desktop: janela de desenvolvimento (Tauri debug) com backend lançado pelo Rust; `.app` e `.dmg` gerados; a `.app` arranca o backend empacotado, cria a pasta de dados e, ao sair, termina o backend (0 processos restantes). No backend empacotado: Vosk detectado, 10 vozes pt listadas, tarefa criada por comando.
- Auto-teste de voz: «UAJI» detectado (distância 0,088 / limiar 0,16), pedido transcrito por Vosk, tarefa criada, microfone fechado ao desligar a escuta.
- Capturas (Chrome headless, 1440×1000) do painel holográfico, Assistente e Definições com dados de desenvolvimento.

## Não testado neste ambiente

- **Microfone real**: a detecção de «UAJI» e o STT foram validados com áudio sintetizado injectado no serviço (auto-teste) e com simulações; falta o teste com a sua voz, o pedido de permissão do macOS na app instalada e o comportamento com ruído/eco.
- Carregamento do modelo Vosk dentro do backend empacotado (o pacote e a biblioteca estão incluídos e detectados; a primeira transcrição real acontece com o microfone).
- Chamadas reais à API GitHub e Anthropic (testadas com transportes/fornecedores simulados; requerem credenciais).
- Notificações nativas do macOS (dependem do Tauri).
