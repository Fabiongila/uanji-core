# UANJI CORE — Guia de funcionalidades

**Ideias. Projectos. Futuro.**

O UANJI CORE é um centro de comando pessoal para macOS. Reúne projectos, tarefas, agenda, notas, automações, métricas e código num só lugar, com um assistente por voz e texto que se chama dizendo **«UAJI»**. Funciona sem Internet e sem serviços pagos, e os dados ficam no seu Mac.

Este documento explica o que cada funcionalidade faz, para que serve e onde a encontrar. Para instalar e executar, veja o [README](../README.md).

## Estado de cada funcionalidade

| Marca | Significado |
|---|---|
| ✅ | Implementada e testada |
| 🟡 | Implementada, falta uma validação real (microfone, token ou chave) |
| 🆕 | Nova: implementada e testada; incluída no `.dmg` gerado a 5 de Novembro de 2026, que tem de instalar para a ter |
| ⏳ | Ainda não implementada |

---

## 1. Painel inicial ✅

É o ecrã de arranque: cards holográficos com dados reais e o núcleo do assistente.

| Card | O que mostra |
|---|---|
| Tarefas | Pendentes, concluídas hoje, atrasadas e as tarefas prioritárias |
| Projectos | Projectos activos com progresso circular, bloqueios e actividade recente |
| Assistente UANJI | Núcleo, microfone, escuta, últimas mensagens e pedidos rápidos |
| Alertas e recomendações | Atrasos, projectos bloqueados ou parados, automações falhadas |
| Agenda de hoje | Compromissos e prazos do dia |
| Desempenho | Concluídas em 7 dias, tempo de foco, tendência e controlo de foco |
| Conhecimento | Total de notas e as mais recentes |
| Automações | Activas, próxima execução e falhas |
| Integrações | Estado das ligações |
| Sistema | Backend, base de dados, disco, cofre e voz |

Cada card abre a sua área. Em **Personalizar painel** pode mover, redimensionar e esconder cards.

---

## 2. Trabalho

### Projectos ✅
- Estados: planeado, activo, em pausa, bloqueado (com motivo), concluído e arquivado.
- Prioridade, datas, descrição, objectivos, resultados esperados, marcos, links e histórico.
- Progresso calculado: tarefas concluídas ÷ tarefas não arquivadas.
- Criação a partir de um modelo, com checklist e tarefas numa só operação.

### Tarefas ✅
- Vista em lista e em Kanban, com arrastar ou teclado.
- Subtarefas, dependências (com detecção de ciclos) e bloqueios com motivo.
- Prazos com fuso horário, prioridades, estimativas e critérios de conclusão.
- Contagem de adiamentos e filtros por estado, prioridade, prazo e projecto.
- 🆕 Número curto **UJ-41**, para referir a tarefa em commits, branches e pull requests.

### Sessões de foco ✅
Cronómetro ou registo manual, ligado a uma tarefa ou a um projecto.

### Agenda ✅
Vista de dia e de semana, eventos, blocos de trabalho e tarefas com prazo. É local: não sincroniza com calendários externos.

### Revisão diária e planeamento semanal ✅
Áreas próprias para rever o dia e planear a semana com os dados registados.

### Checklists e modelos ✅
Sete modelos editáveis:
1. Novo projecto de software
2. Desenvolvimento de uma API
3. Revisão de código
4. Publicação de uma aplicação
5. Preparação de um projecto de análise de dados
6. Recolha e validação de datasets
7. Revisão semanal

---

## 3. Conhecimento ✅

- **Notas em Markdown:** gravação automática, revisões, detecção de conflitos, rascunho local e arquivo.
- **Tipos de nota:** nota, decisão, ideia, conceito, solução, erro, documentação, referência e lição.
- **Relações explícitas** entre notas, tarefas e projectos, com vista em grafo.
- **Pesquisa global** em projectos, tarefas, notas, eventos e automações, tolerante a acentos.

---

## 4. Automação visual

Um editor de fluxos com nós ligados: **Gatilho → Condição → Acção → Resultado**.

### Gatilhos

| Gatilho | Quando dispara | Estado |
|---|---|---|
| Manual | Botão, ⌘K | ✅ |
| Agendado | Por intervalo, todos os dias a uma hora, ou uma vez | ✅ |
| Tarefa concluída | Ao concluir uma tarefa, opcionalmente de um projecto | ✅ |
| Prazo próximo | Antes do prazo de uma tarefa | ✅ |
| Webhook | Outra aplicação deste Mac envia um POST com segredo | 🆕 |
| Evento do GitHub | Novo commit, PR aberto ou integrado, nova issue ou release (verificado de 5 em 5 minutos) | 🆕 |
| Abrir uma aplicação | Quando uma app passa para primeiro plano (requer o monitor de actividade; no máximo uma vez a cada 30 minutos) | 🆕 |

### Condições 🆕
Um nó de condição fica antes de uma acção. Se as regras não se verificarem, pode **ignorar a acção seguinte** ou **parar o fluxo**. Operadores: igual, diferente, contém, existe e não existe.

### Acções ✅
Criar tarefa, actualizar o estado de uma tarefa ou de um projecto, criar nota, gerar resumo local e 🆕 executar outro fluxo.

### Resultados
Registar evento e mostrar notificação ✅; 🆕 falar em voz alta e chamar um webhook externo.

### Garantias ✅
- Versões de cada automação, com reposição.
- Histórico de cada execução e de cada etapa.
- Tempo limite, cancelamento e protecção contra execuções duplicadas.
- Só acções internas validadas; nunca código arbitrário.
- Uma falha pára o fluxo, mas as etapas anteriores não são desfeitas.

---

## 5. Desempenho

### Métricas ✅
Por período, tendências, por projecto, tempo de foco e execuções de automações, com tabela alternativa aos gráficos.

### Centro de desempenho 🆕
Vai além de contar tarefas:

| Medida | Como é calculada |
|---|---|
| Tempo de ciclo | Da primeira vez «em curso» até à conclusão (média, mediana e percentil 85) |
| Criação → conclusão | Tempo total desde que a tarefa foi criada |
| Tarefas bloqueadas | Bloqueadas agora, há quanto tempo, e tempo bloqueado acumulado |
| Interrupções | Sessões de foco com menos de 25 minutos e tarefas que saíram de «em curso» sem serem concluídas |
| Mudanças de aplicação por hora | Só com o monitor de actividade ligado |
| Progresso por objectivo | Tarefas concluídas ÷ tarefas ligadas ao objectivo |
| Evolução semanal | Estas medidas semana a semana (4, 8 ou 12 semanas), com filtro por projecto |

Os **objectivos** criam-se aqui e ligam-se às tarefas no detalhe de cada tarefa.

Nas tarefas que já existiam, o tempo de ciclo só conta para as que estavam em curso à data da actualização, a partir desse momento.

---

## 6. Integração com desenvolvimento

- **GitHub** 🟡 (só leitura): ligação, metadados, commits e pull requests. Testado com respostas simuladas; falta um token real.
- **Branches, issues, releases e tags** 🆕 🟡: separador **Código** do projecto. Falta o mesmo teste real.
- **Repositórios locais** 🆕: uma pasta com Git ligada ao projecto; não precisa de token nem de Internet.
- **Ligar código a tarefas** 🆕: escreva **UJ-41** num commit, branch, pull request ou issue. Em «Ligar código às tarefas», a alteração fica associada à tarefa 41 e aparece no detalhe dela.
- **Versões** 🆕: separador **Versões** do projecto (ex.: v0.4), com tarefas associadas, progresso, tag Git e alterações de código.

---

## 7. Command Palette (⌘K)

| Acção | Estado |
|---|---|
| Procurar projectos, tarefas, notas, eventos e automações | ✅ |
| Criar tarefa, projecto ou nota com o texto escrito | ✅ |
| Navegar para qualquer área | ✅ |
| Abrir ficheiros dos seus projectos (no VS Code, se instalado) | 🆕 |
| Executar fluxos | 🆕 |
| Chamar comandos (foco, relatório do dia, nova automação) | 🆕 |
| Pedir ao assistente com o texto escrito | 🆕 |

A pesquisa de ficheiros usa as pastas ligadas aos projectos e as pastas indicadas em **Actividade**.

Há também a **barra de comando (⌘J)** ✅, por exemplo: `tarefa Rever PR !alta @amanhã`, `concluir parte-do-título`, `foco iniciar`, `ir para agenda`.

---

## 8. Assistente UANJI

### Activação e voz 🟡
- Dizer **«UAJI»** (detecção local, com amostras da sua voz) ou carregar no microfone.
- Reconhecimento de fala local, em português, sem Internet.
- Respostas faladas com as vozes do macOS: feminina ou masculina, velocidade, volume e idioma.
- Interromper com Esc e retomar a leitura.

Validado com áudio sintetizado. Falta testar com o seu microfone e a sua voz.

### Conversa ✅
Texto e voz seguem o mesmo caminho. Inclui perguntas de seguimento, contexto («este projecto»), «repete», «cancela», «sim/não», escolha entre opções e histórico com retenção configurável.

### Acções reais ✅
O assistente usa 34 ferramentas internas validadas, por nível de risco:

| Risco | Quantas | Confirmação |
|---|---|---|
| Consulta | 17 | Nunca |
| Acção no sistema | 4 | Configurável; desligada por omissão |
| Cria dados | 5 | Configurável; desligada por omissão |
| Altera dados | 4 | Configurável; ligada por omissão |
| Destrutiva | 4 | Sempre |

Tudo o que um modelo de IA propõe escrever pede sempre confirmação.

### Relatórios por voz ✅
Do dia, semanal, estado dos projectos, próximos passos, automações e principais problemas. Cada um separa factos registados, cálculos, recomendações e o que não se sabe.

### Personalidade ✅
Forma de tratamento masculina, feminina, neutra ou personalizada. É sempre escolhida por si; o género nunca é deduzido.

### Núcleo visual ✅
Mostra o estado real: inactivo, à espera de «UAJI», a ouvir, a interpretar, a preparar, a falar, a executar, a aguardar confirmação, concluído ou erro.

### Modelo de IA
- **Sem IA** ✅: os pedidos frequentes em português são interpretados localmente.
- **Claude** 🟡: testado com fornecedor simulado; falta uma chave real.
- **O seu próprio modelo** 🆕 🟡: qualquer servidor compatível com a API OpenAI, como Ollama, LM Studio, llama.cpp ou OpenRouter. Configura-se em Definições → Assistente de IA, com «Guardar e testar ligação». Testado com servidor simulado; falta um modelo real. Para executar acções, o modelo tem de suportar «tools»/«function calling».

---

## 9. Autonomia

### Iniciativa própria 🟡
O assistente fala sem esperar por um clique:

| Regra | Quando |
|---|---|
| Bom dia | Primeira verificação entre as 5h e as 13h |
| Bem-vindo de volta | Regresso depois de 20 minutos ou mais fora |
| Prazos | Tarefa a vencer na próxima hora |
| Compromissos | Evento nos próximos 10 minutos |
| Automações | Execução falhada |
| Foco longo | Sessão com 50 minutos ou mais |
| Pausas | 90 minutos activos sem pausa |
| Mudanças de contexto | Muitas trocas de aplicação em 15 minutos |
| Sugestões | 30 minutos a programar num projecto ou numa pasta sem projecto |
| Fim do dia | Depois da hora da revisão diária |

Quando faz uma pergunta, responde-se por voz («sim», «agora não») ou por botão. Respeita horas de silêncio e reuniões, tem limite de frequência e não repete avisos. Cada regra pode ser desligada. Falta validar a resposta por voz com o microfone.

### Monitor de actividade ✅ (opcional, desligado por omissão)
Página **Actividade**: o que está a fazer agora, o resumo do dia, os padrões dos últimos 14 dias e os commits do dia.

- **Regista:** a aplicação em primeiro plano, o tempo de inactividade, a pasta do VS Code e, se quiser, o título das janelas.
- **Nunca regista:** teclas, conteúdo, capturas de ecrã ou sites visitados.
- **Controlo:** apps excluídas, retenção configurável e apagamento total.

### Acções no Mac ✅
«abre o VS Code», «fecha o Chrome», «volume a 30», «pesquisa na web …», «abre a pasta …», «como está a bateria?», «que aplicações estão abertas?». Testadas com execução simulada.

**Comandos de terminal:** desligados por omissão. Cada comando é mostrado e só corre depois de confirmar. `sudo`, formatação de discos e apagar a pasta pessoal são sempre recusados.

### Adaptação ✅
Relatórios, o bom-dia e o contexto da IA usam os seus hábitos reais. Os padrões precisam de pelo menos 3 dias de dados.

---

## 10. Personalização ✅

- **Temas:** UANJI, Abismo, Âmbar, Alto contraste e Claro.
- **Cor de destaque:** ciano, azul, âmbar, esmeralda ou violeta.
- **Densidade**, tamanho da interface (85–130 %) e barra lateral à esquerda ou à direita.
- **Painel:** ordem, tamanho e visibilidade dos cards.
- **Disposição adaptativa:** os cards que mais usa sobem; alertas e atrasos ficam sempre à frente.
- **Reduzir animações**, para hardware antigo.

---

## 11. Segurança e dados ✅

- **Cofre de segredos** no Keychain do macOS; os segredos nunca vão para a base de dados, os logs ou a IA.
- **Backups** manuais e automáticos, com verificação, teste de restauro, restauro com cópia prévia, importação e exportação em JSON.
- **Backend local:** token por sessão, só aceita ligações locais e exige confirmação nas eliminações.
- 🆕 **Webhooks:** só ligações locais, com segredo por automação; só o hash do segredo é guardado.
- **Microfone:** fechado por omissão, com indicador permanente. O áudio nunca é gravado nem enviado; a excepção são as amostras de «UAJI» que grava de propósito.
- **Diagnóstico e logs** com segredos ocultados; os erros da interface ficam registados.

---

## 12. Aplicação desktop ✅

App macOS (`.app` e `.dmg`) com o backend incluído, para Intel. Arranca e fecha sem deixar processos para trás. A aplicação não está assinada nem notarizada, porque isso requer uma conta Apple Developer.

---

## 13. O que ainda falta

- **Validar consigo:** a voz com o microfone real; um token GitHub; uma chave Claude; um modelo próprio real.
- **Interface dourada:** os painéis que vêm para a frente existem só como protótipo em `design-prototipos/`; ainda não estão na app.
- **Assistente e novas áreas:** o assistente ainda não responde sobre tempo de ciclo, objectivos ou versões.
- **Calendários externos:** ainda não há sincronização.
- **GitHub:** só lê; não escreve nem sincroniza issues com tarefas.
- **Automações:** os fluxos são sequenciais; uma condição ignora ou pára, mas não abre dois caminhos.
- **Vozes:** o macOS não tem vozes de português de Angola; usam-se pt-PT e pt-BR.

## Documentação técnica

| Documento | Conteúdo |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arquitectura e módulos |
| [DATA_MODEL.md](DATA_MODEL.md) | Entidades e regras de integridade |
| [VOICE.md](VOICE.md) | Voz e assistente |
| [AUTONOMY.md](AUTONOMY.md) | Iniciativa, actividade e acções no sistema |
| [SECURITY.md](SECURITY.md) | Modelo de segurança |
| [TESTING.md](TESTING.md) | Testes |
| [ROADMAP.md](ROADMAP.md) | Estado e próximos passos |
