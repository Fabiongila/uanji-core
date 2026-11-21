# UANJI CORE

**Ideias. Projectos. Futuro.**

O UANJI CORE é um centro de comando pessoal para macOS. Junta num só lugar projectos, tarefas, agenda, notas, conhecimento, automações, métricas e integrações. Inclui um assistente por voz e texto que se chama dizendo **«UAJI»**, executa acções reais, lê relatórios e toma a iniciativa de falar consigo.

Funciona **sem Internet e sem serviços pagos**. Os dados ficam no seu Mac. O reconhecimento de fala é local, e um fornecedor de IA (Claude) é opcional.

---

## Índice

1. [Visão geral](#visão-geral)
2. [Funcionalidades](#funcionalidades)
3. [Arquitectura e tecnologias](#arquitectura-e-tecnologias)
4. [Requisitos](#requisitos)
5. [Instalação e execução](#instalação-e-execução)
6. [Utilização rápida](#utilização-rápida)
7. [Privacidade e segurança](#privacidade-e-segurança)
8. [Testes e qualidade](#testes-e-qualidade)
9. [Estado actual e limitações](#estado-actual-e-limitações)
10. [Protótipos de interface](#protótipos-de-interface)
11. [Documentação](#documentação)

---

## Visão geral

| Princípio | O que significa na prática |
|---|---|
| **Local primeiro** | Base de dados SQLite no seu Mac; tudo funciona offline. |
| **Dados reais** | Painéis, relatórios e respostas do assistente vêm apenas de registos reais. Quando falta informação, a aplicação diz que não sabe. |
| **Assistente com acções** | Não é só conversa: cria tarefas, abre projectos, executa automações e age no Mac, sempre através de ferramentas validadas. |
| **Controlo do utilizador** | Operações destrutivas exigem confirmação. O microfone e o monitor de actividade estão desligados por omissão. |
| **Pensado para hardware modesto** | Testado num MacBook Air de 2015: animações leves, sem 3D, sem consultas agressivas. |

---

## Funcionalidades

### 1. Trabalho

- **Projectos**
  - Estados: planeado, activo, em pausa, bloqueado (com motivo), concluído, arquivado.
  - Prioridade, datas, objectivos e resultados esperados, marcos, links e histórico de alterações.
  - Progresso calculado a partir das tarefas concluídas.
  - Detecção de projectos parados ou bloqueados.
  - Criação a partir de modelos.
- **Tarefas**
  - Vista em lista e em Kanban, com arrastar e largar ou navegação por teclado.
  - Subtarefas, dependências (com detecção de ciclos) e bloqueios com motivo.
  - Prazos com fuso horário, prioridades, estimativas, critérios de conclusão e contagem de adiamentos.
  - Filtros por estado, prioridade, prazo e projecto.
- **Sessões de foco**: cronómetro ou registo manual, associadas a tarefas ou projectos.
- **Agenda**: vista de dia e de semana, eventos, blocos de trabalho e tarefas com prazo.
- **Revisão diária e planeamento semanal**, baseados nos dados reais.
- **Checklists e modelos**: 7 modelos editáveis incluídos:
  - novo projecto de software;
  - desenvolvimento de uma API;
  - revisão de código;
  - publicação de uma aplicação;
  - análise de dados;
  - recolha e validação de datasets;
  - revisão semanal.

### 2. Conhecimento

- **Notas em Markdown**: gravação automática, histórico de revisões, detecção de conflitos, rascunho local e arquivo.
- **Base de conhecimento** com tipos: nota, decisão, ideia, conceito, solução, erro, documentação, referência e lição.
- **Relações explícitas** entre notas, tarefas e projectos, com vista em grafo.
- **Pesquisa global** em projectos, tarefas, notas, eventos e automações, tolerante a acentos.

### 3. Automações

- **Gatilhos**: manuais, agendados, eventos internos (tarefa concluída, prazo próximo) e **eventos externos**: webhook de outra aplicação, GitHub (commit, PR, issue, release) e abrir uma aplicação no Mac.
- **Construtor visual** com nós ligados: Gatilho → Condição → Acção → Resultado.
- **Condições** antes de cada acção: se falharem, ignoram essa acção ou param o fluxo.
- **Resultados**: notificação, voz, registo no histórico ou webhook para outra aplicação.
- **Versões** de cada automação, com reposição de versões anteriores.
- **Histórico** de cada execução e de cada etapa.
- **Garantias**: tempo limite, protecção contra execuções duplicadas e cancelamento.
- **Segurança**: só acções internas tipadas; nunca código arbitrário.

### 4. Desempenho e painel inicial

- **Painel inicial com cards holográficos** e dados reais: Tarefas, Projectos, Assistente, Alertas, Agenda, Desempenho, Conhecimento, Automações, Integrações e Sistema.
- **Métricas**: por período, tendências, por projecto, tempo de foco registado e execuções de automações, com tabela alternativa aos gráficos.
- **Centro de desempenho**: tempo de ciclo (início → conclusão), tempo bloqueado, interrupções, progresso por objectivo e evolução semanal.
- **Alertas**: tarefas atrasadas, projectos bloqueados ou parados, automações falhadas.
- **Notificações** internas e nativas do macOS, com horas de silêncio e escolha de categorias.

### 5. Assistente UANJI (voz e texto)

- **Activação**
  - Dizer **«UAJI»**: detecção local, com amostras gravadas da sua voz.
  - Ou carregar no botão do microfone.
- **Reconhecimento de fala local** (Vosk, português). Não precisa de Internet nem envia áudio para fora.
- **Respostas faladas**
  - Vozes do macOS: feminina ou masculina, com velocidade, volume e idioma configuráveis.
  - Interromper com Esc e retomar a leitura.
- **Conversa natural**
  - Perguntas de seguimento e contexto («o que está a bloquear *este* projecto?»).
  - «repete», «cancela», «sim/não» e escolha entre opções.
  - Histórico com retenção configurável.
- **Funciona sem IA**: os pedidos frequentes em português são interpretados localmente. Com um fornecedor de IA configurado, há também conversa livre.
- **O seu próprio modelo**: além do Claude, aceita qualquer servidor compatível com a API OpenAI (Ollama, LM Studio, llama.cpp, OpenRouter).
- **Acções reais**
  - Criar tarefas, notas, ideias, projectos e checklists.
  - Concluir ou mudar o estado de tarefas.
  - Iniciar ou terminar foco e executar automações.
  - Arquivar ou eliminar, sempre com confirmação e com a descrição do que vai mudar.
- **Relatórios por voz**: do dia, semanal, estado dos projectos, próximos passos, automações e principais problemas. Cada relatório separa:
  - factos registados;
  - cálculos derivados;
  - recomendações;
  - informação indisponível.
- **Forma de tratamento** escolhida por si: masculina, feminina, neutra ou personalizada. O género nunca é deduzido.
- **Núcleo visual** que mostra o estado real do assistente: inactivo, à espera de «UAJI», a ouvir, a interpretar, a preparar, a falar, a executar, a aguardar confirmação, concluído e erro.

Exemplos de pedidos:

- «UAJI, quais são as minhas tarefas prioritárias de hoje?»
- «Qual dos meus projectos está mais atrasado?»
- «Cria uma tarefa para rever a autenticação do Q360 para amanhã.»
- «Regista uma ideia: usar cache na API.»
- «Faz o relatório do meu dia.»
- «Mostra-me as automações que falharam.»

### 6. Autonomia

- **Iniciativa própria**: o assistente fala consigo sem esperar por um clique.
  - Bom dia com o plano do dia.
  - Boas-vindas quando regressa ao computador.
  - Prazos a 1 hora e compromissos a 10 minutos.
  - Sugestões de pausa e de sessão de foco.
  - Automações que falharam.
  - Resumo no fim do dia.
  - Quando pergunta algo («Quer que leia as prioridades?»), responde por voz («sim», «agora não») ou com um botão.
  - Respeita horas de silêncio e reuniões, e tem limite de frequência.
- **Monitor de actividade** (opcional, só local)
  - O que regista: a aplicação em primeiro plano, o tempo de inactividade, a pasta aberta no VS Code e os seus commits Git do dia.
  - O que nunca regista: teclas, conteúdo ou capturas de ecrã.
  - Página **Actividade** com o resumo do dia e os padrões dos últimos 14 dias.
- **Acções no Mac**
  - Abrir e fechar aplicações; abrir sites, pesquisas e pastas.
  - Ajustar o volume; ver bateria, disco e aplicações abertas.
  - **Comandos de terminal**: desligados por omissão e sempre confirmados.
- **Adaptação**: relatórios e respostas usam os seus hábitos reais (hora de início, horas mais intensas, aplicações e projectos com mais tempo).

### 7. Personalização

- **Temas**: UANJI (azul-noite), Abismo, Âmbar, Alto contraste e Claro.
- **Cor de destaque**: ciano, azul eléctrico, âmbar, esmeralda ou violeta.
- **Densidade**, tamanho da interface (85–130 %) e barra lateral à esquerda ou à direita.
- **Painel personalizável**: mover, redimensionar e esconder cards.
- **Disposição adaptativa**: os cards que mais usa sobem; alertas e atrasos ficam sempre à frente.
- Opção para **reduzir animações**.

### 8. Integrações e comandos

- **GitHub** (só leitura): commits, branches, pull requests, issues e releases.
- **Repositórios locais**: uma pasta com Git ligada ao projecto, sem token.
- **Código ↔ tarefas ↔ versões**: escreva `UJ-41` num commit, branch ou PR para o ligar à tarefa 41; agrupe tarefas em versões do projecto.
- **Command Palette (<kbd>⌘K</kbd>)**: procurar, criar tarefas, abrir ficheiros, executar fluxos, chamar comandos e pedir ao assistente.
- **Barra de comando (<kbd>⌘J</kbd>)**: por exemplo, `tarefa Rever PR !alta @amanhã`, `projecto Nome`, `concluir parte-do-título`, `foco iniciar`, `ir para agenda`.

### 9. Segurança e dados

- **Cofre de segredos** no Keychain do macOS. Os segredos nunca vão para a base de dados, os logs ou o modelo de IA.
- **Backups**
  - Manuais e automáticos.
  - Verificação de integridade e teste de restauro numa cópia.
  - Restauro com cópia de segurança prévia.
  - Importação e exportação em JSON.
- **Backend local protegido**: token por sessão, aceita apenas ligações locais e exige confirmação em todas as eliminações.
- **Diagnóstico e logs** com segredos ocultados. Os erros da interface ficam registados para análise.

### 10. Aplicação desktop

- App macOS (`.app` e `.dmg`) com o backend incluído.
- Arranca e fecha sem deixar processos para trás.
- Pede autorização para o microfone com uma mensagem própria.

---

## Arquitectura e tecnologias

```
┌──────────── Tauri 2 (janela macOS) ────────────┐
│  React 19 + TypeScript  ←→  backend local      │
│  (interface, núcleo,       FastAPI + SQLite    │
│   painéis, ⌘K)             (127.0.0.1, token)  │
└────────────────────────────────────────────────┘
         │                         │
   eventos em tempo real     serviços: projectos, tarefas, notas,
   (voz, iniciativa)         automações, métricas, backups, cofre,
                             assistente, voz, actividade, sistema
```

| Camada | Tecnologias |
|---|---|
| **Interface** | React 19, TypeScript (strict), Vite, Tailwind CSS 4, TanStack Query, Zustand, React Hook Form + Zod, Recharts, React Flow |
| **Backend** | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, SQLite com FTS5, `keyring` (Keychain) |
| **Voz** | Vosk (fala → texto, local), detector próprio da palavra de activação (MFCC + DTW), `say` do macOS (texto → fala), PortAudio |
| **macOS** | PyObjC (AVFoundation, AppKit, Quartz) para permissões, vozes, aplicação activa e inactividade |
| **Desktop** | Tauri 2 (Rust) e PyInstaller para empacotar o backend |
| **IA (opcional)** | SDK Anthropic (Claude), apenas através de ferramentas internas tipadas |

Estrutura do repositório:

```
backend/uanji/      API, serviços, automações, assistente, voz, actividade, sistema
frontend/src/       páginas, componentes, núcleo visual, estado da voz
src-tauri/          aplicação desktop (Rust)
docs/               documentação técnica
scripts/            dev.sh, dev-desktop.sh, build-app.sh
design-prototipos/  protótipos de interface (HTML local)
```

---

## Requisitos

Verificados neste computador:

| Componente | Versão | Notas |
|---|---|---|
| macOS | 14.8.9 (Sonoma, via OpenCore Legacy Patcher) | MacBook Air 2015, Intel i5-5250U, x86_64, 8 GB |
| Python | 3.12 | SQLite com FTS5 |
| Node.js | 24 / npm 11 | |
| Xcode Command Line Tools | instaladas | necessárias para Rust e Tauri |
| Rust | 1.99 (rustup) | janela desktop e empacotamento |

---

## Instalação e execução

```bash
# Backend
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev,voice,assistant]"   # "voice": Vosk, PortAudio, AVFoundation; "assistant": SDK Anthropic (opcional)

# Frontend
cd ../frontend
npm install
```

### No browser (desenvolvimento, não requer Rust)

```bash
./scripts/dev.sh
```

O backend fica em `127.0.0.1:8765` e a interface em <http://127.0.0.1:1420>. Os dados de desenvolvimento ficam em `./.dev-data`, separados dos da aplicação instalada. O token é gerado em `./.dev-token` e injectado pelo proxy do Vite; nunca entra no código do frontend.

### Janela desktop e aplicação instalável

```bash
# Uma vez: instalar Rust (altera ~/.cargo e ~/.rustup)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
rustup target add x86_64-apple-darwin

./scripts/dev-desktop.sh      # janela de desenvolvimento
./scripts/build-app.sh        # testes + backend empacotado + .app e .dmg
```

Os ficheiros gerados ficam em `src-tauri/target/x86_64-apple-darwin/release/bundle/`. A aplicação instalada guarda os dados em `~/Library/Application Support/com.uanji.core/` (base de dados, `backups/`, `logs/`, `voice/`).

---

## Utilização rápida

| Acção | Como |
|---|---|
| Pesquisa global e acções rápidas | <kbd>⌘K</kbd> |
| Barra de comando | <kbd>⌘J</kbd> |
| Falar com o assistente | Dizer «UAJI» (com a escuta ligada) ou carregar no microfone |
| Interromper a fala | <kbd>Esc</kbd> |
| Configurar voz e tratamento | Definições → **Voz e personalidade** (instalar o modelo de fala de 31 MB, gravar 3–5 amostras de «UAJI») |
| Ligar o monitor de actividade | **Actividade** → *Ligar o monitor* |
| Criar projecto a partir de modelo | Projectos → *A partir de modelo* |
| Nova automação | Automações → *Nova automação* → *Validar e guardar* |
| Personalizar o painel | Início → *Personalizar painel* |
| Mudar tema e cores | Definições → **Aparência e disposição** |
| Backup e restauro | Backups → *Criar*, *Verificar*, *Testar restauro*, *Restaurar* |

Auto-teste da voz sem microfone: `cd backend && .venv/bin/python -m uanji.voice.selftest`.

---

## Privacidade e segurança

- **Áudio**: processado localmente, nunca gravado nem enviado. Excepção: as amostras de «UAJI» que o utilizador grava explicitamente.
- **Microfone**: fechado por omissão. Um indicador permanente mostra quando está aberto.
- **Monitor de actividade**: desligado por omissão, só local, com exclusão de aplicações, retenção configurável e apagamento total.
- **IA opcional**: recebe apenas texto, nunca segredos, e as escritas que propõe exigem sempre confirmação. Com um modelo local, as conversas não saem do Mac.
- **Webhooks**: só ligações locais, com segredo por automação (guardado apenas como hash).
- **Terminal**: desligado por omissão. Cada comando é mostrado e confirmado; `sudo`, formatação de discos e apagar a pasta pessoal são sempre recusados.
- **Backend**: só aceita pedidos locais com o token da sessão.

Detalhes em [docs/SECURITY.md](docs/SECURITY.md).

---

## Testes e qualidade

```bash
cd backend && .venv/bin/pytest && .venv/bin/ruff check uanji tests && .venv/bin/mypy uanji
cd frontend && npx vitest run && npx tsc -b --noEmit
```

- **Backend**: 97 testes. Cobrem:
  - projectos, tarefas, notas, pesquisa, automações, backups e segurança;
  - assistente, voz (com microfone simulado), iniciativa, actividade e acções no sistema.
- **Frontend**: 43 testes. Cobrem:
  - navegação, formulários, painel e editor de automações;
  - assistente, voz, temas e personalização do painel.
- Lint (ruff) e tipos em modo estrito (mypy, TypeScript).

Detalhes em [docs/TESTING.md](docs/TESTING.md).

---

## Estado actual e limitações

| Área | Estado |
|---|---|
| Funcionalidades de trabalho, conhecimento, automações, métricas, backups e cofre | ✅ implementadas e testadas |
| Aplicação desktop (`.app`/`.dmg`) | ✅ gerada e verificada (arranque e encerramento) |
| Assistente, relatórios e acções | ✅ testados; reconhecimento de fala validado com áudio sintetizado |
| Palavra «UAJI» e reconhecimento com o **microfone real e a sua voz** | 🟡 por validar consigo |
| Iniciativa do assistente e monitor de actividade | ✅ verificados na aplicação real; padrões precisam de alguns dias de dados |
| GitHub, Claude e modelo próprio | 🟡 testados com respostas simuladas; precisam de token, chave ou modelo reais |
| Repositórios locais e ligação de commits e branches a tarefas | ✅ testados com repositórios Git reais |
| Interface com painéis dourados que vêm para a frente | ⏳ em protótipo, a aplicar à app após aprovação |
| Vozes de português de Angola | ⚠️ não existem no macOS; usam-se vozes pt-PT e pt-BR |
| Assinatura e notarização Apple | ⏳ requer conta Apple Developer |

Plano completo em [docs/ROADMAP.md](docs/ROADMAP.md).

---

## Protótipos de interface

A pasta `design-prototipos/` contém protótipos que abrem localmente no browser (comece por `index.html`):

- **Protótipo interactivo**: a imagem de referência com o núcleo dourado e os painéis. Ao clicar, cada painel vem para a frente e mostra a funcionalidade completa. Inclui painéis novos para Espaços, Desempenho, GitHub, Conhecimento, Actividade, Definições e Comandos (⌘K).
- **Opções A, A2, B e C**: direcções visuais alternativas (Constelação Dourada, Núcleo Ciano, Ponte de Comando).

---

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/FUNCIONALIDADES.md](docs/FUNCIONALIDADES.md) | **Guia de todas as funcionalidades** e o estado de cada uma |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Arquitectura, módulos e ciclo de vida do backend |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Entidades, relações e regras de integridade |
| [docs/VOICE.md](docs/VOICE.md) | Assistente por voz: escolhas técnicas, comandos, confirmações e testes |
| [docs/AUTONOMY.md](docs/AUTONOMY.md) | Iniciativa, monitor de actividade, acções no sistema e adaptação |
| [docs/SECURITY.md](docs/SECURITY.md) | Modelo de segurança e limitações |
| [docs/TESTING.md](docs/TESTING.md) | Testes e comandos |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Estado das funcionalidades e próximos passos |
