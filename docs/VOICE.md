# Assistente UANJI: voz, comandos e relatórios

O assistente funciona **sem Internet e sem serviços pagos** para os pedidos frequentes (interpretação
local em português). Um fornecedor de IA (Anthropic) é opcional e só recebe **texto**, nunca áudio.

## Arquitectura

```
Microfone ──► capture.Microphone (PortAudio, 16 kHz, blocos de 30 ms)
                │
                ▼
          dsp.Segmenter (VAD por energia, limiar adaptativo)
                │ enunciado curto                      │ pedido
                ▼                                      ▼
          wake.WakeDetector (MFCC + DTW)         stt.VoskEngine (streaming, local)
                │ «UAJI»                               │ texto
                ▼                                      ▼
          tts.Speaker (saudação)            assistant.conversation.Assistant
                                               ├─ intents.Parser (regras locais, pt)
                                               ├─ tools (ferramentas tipadas, risco)
                                               ├─ actions (confirmações, execução)
                                               ├─ reports (factos/cálculos/recomendações)
                                               └─ core (fornecedor de IA, opcional)
                                                       │ resposta
                                                       ▼
                                               tts.Speaker (say, frase a frase)
```

`voice/service.py` (VoiceService) coordena os módulos e publica eventos por SSE
(`GET /api/voice/events`): estado, transcrição parcial, transcrição final e respostas.
Cada módulo é substituível (os testes usam microfone, STT e TTS simulados).

| Módulo | Ficheiro | Responsabilidade |
|---|---|---|
| Palavra de activação | `voice/wake.py` | compara enunciados curtos com amostras (MFCC + DTW) |
| Captura de áudio | `voice/capture.py` | microfone, conversão para 16 kHz, permissões AVFoundation |
| STT | `voice/stt.py` | Vosk em streaming; instalação do modelo a pedido |
| Conversa | `assistant/conversation.py` | contexto, seguimento, confirmações por voz, repetição, histórico |
| Intenções | `assistant/intents.py` | regras em português (sem IA) |
| Ferramentas | `assistant/tools.py` | únicas operações permitidas, com nível de risco |
| Execução | `assistant/actions.py` | transacção própria; sucesso só após *commit* |
| Relatórios | `assistant/reports.py` | só dados registados, secções separadas |
| TTS | `voice/tts.py` | vozes instaladas no macOS; interromper e retomar |
| Estados | `voice/service.py` | máquina de estados + eventos para a interface |

## Escolhas técnicas (MacBook Air 2015, Intel i5, macOS 14 via OCLP)

**Palavra de activação — MFCC + DTW por amostras (estilo Raven/Rhasspy).**
- Porquê: «UAJI» não existe no vocabulário dos modelos de fala (Vosk ignora-a); os motores
  comerciais (Porcupine) exigem conta/chave e modelo treinado por palavra; o openWakeWord usa
  ONNX e um modelo por palavra, mais pesado e sem «UAJI».
- Custo: só a energia de cada bloco de 30 ms é calculada continuamente; o DTW (~20–40 ms) corre
  apenas quando termina um enunciado curto (< 1,8 s).
- Sem amostras próprias, usam-se amostras geradas com vozes do sistema (Joana, Luciana, Eddy).
  Funcionam com outras vozes sintéticas (auto-teste: distância 0,088 com limiar 0,16), mas
  **a fiabilidade com a voz real exige gravar 3 a 5 amostras** em Definições → Voz e personalidade.
- Não se usa o reconhecimento de voz do WebView/browser: não permite escuta contínua fiável em
  segundo plano e, no Safari/WebKit, depende dos serviços da Apple.

**STT — Vosk, modelo pequeno de português (31 MB).**
- Medido nesta máquina: carregamento 3,8 s; transcrição de 3,2 s de fala em ~1,8 s (streaming em
  blocos de 200 ms) + 0,6 s após o fim; ~160 MB de memória. Carregado só na primeira utilização.
- O modelo é português do Brasil/Portugal genérico; nomes próprios (ex.: «Q360») podem ser mal
  transcritos. O texto pode ser corrigido escrevendo.
- Alternativa avaliada: Whisper local (whisper.cpp) — demasiado lento nesta CPU sem GPU suportada.

**TTS — comando `say` do macOS.** Local, sem dependências, interrompível (o processo é terminado)
e lido frase a frase para retomar a partir da frase interrompida. Volume aplicado com o comando
embebido `[[volm]]`.

## Comportamento real da escuta

| Situação | Comportamento |
|---|---|
| Escuta desligada (omissão) | Microfone fechado. Só abre ao carregar no botão do microfone, para um pedido, e fecha a seguir. |
| Escuta ligada, app aberta ou minimizada | Microfone aberto; análise local contínua; indicador «Microfone aberto» na barra superior. |
| Mac em repouso | O macOS suspende o áudio; retoma ao acordar. |
| App fechada | O backend termina; nada é escutado. Ao reabrir, a preferência de escuta é reposta. |
| Assistente a falar | O áudio do microfone é ignorado (evita ouvir-se a si próprio). Interromper: botão, tecla Esc. |
| Depois de responder | Janela de seguimento (8 s, configurável) para continuar sem repetir «UAJI». |

O áudio **nunca** é gravado em disco (excepto as amostras da palavra de activação que o utilizador
grava explicitamente, guardadas na pasta de dados) e **nunca** é enviado para fora.

## Permissões do microfone

- App instalada: o macOS pede autorização com a mensagem de `src-tauri/Info.plist`
  (`NSMicrophoneUsageDescription`); o backend (processo filho) herda a permissão da app.
- Desenvolvimento: a permissão é atribuída ao Terminal que lançou o processo.
- Negada: a interface mostra «Microfone negado» e explica como autorizar em Definições do Sistema.
  A escuta não arranca e o texto continua a funcionar.
- Antes da primeira utilização, a interface explica a finalidade e o processamento local.

## Vozes e tratamento

- Só são listadas vozes instaladas (`say -v ?`), com género declarado pelo sistema; as vozes
  «Eloquence» (Eddy, Reed, Rocko, Grandpa, Flo, Sandy, Shelley, Grandma) não o declaram e usam a
  classificação publicada pela Apple (marcada «catálogo Apple» na interface).
- Neste Mac: pt-PT feminina (Joana); pt-BR femininas (Luciana, Flo, Sandy, Shelley, Grandma) e
  masculinas (Eddy, Reed, Rocko, Grandpa). **Não há voz pt-PT masculina nem pt-AO** instalada:
  a interface explica a limitação e como instalar mais vozes.
- Forma de tratamento (masculino, feminino, neutro, personalizado) escolhida pelo utilizador; usada
  com moderação (saudação, introdução de relatórios). Não se deduz o género do nome nem da voz.
  Não foi implementada qualquer estimativa a partir da voz: não é fiável e não é necessária.

## Comandos reconhecidos localmente (exemplos)

Consultas: tarefas prioritárias / atrasadas / de hoje / desta semana, projecto mais atrasado, estado
dos projectos, o que bloqueia «este projecto», resumo de um projecto, agenda de hoje/amanhã,
automações falhadas/executadas hoje, desempenho, pesquisa, «abre …».
Relatórios: do dia, semanal, projectos, próximos passos, automações, problemas.
Acções: criar tarefa (com «no projecto X», «para amanhã», «urgente»), concluir/mudar estado, registar
ideia/nota/decisão, criar projecto, checklist a partir de modelo, iniciar/terminar foco, executar
automação, arquivar/eliminar.
Controlo: «sim», «não», «repete», «cancela», «continua», «ajuda».

Pedidos não reconhecidos vão para o fornecedor de IA, se configurado; senão o assistente diz que não
percebeu e dá exemplos. Checklists personalizadas (ex.: «publicar uma API Django») usam a IA quando
existe; sem IA, usam o modelo existente mais próximo e dizem-no.

## Confirmações

| Risco | Exemplos | Confirmação |
|---|---|---|
| Consulta | listar, relatórios, navegar | nunca |
| Cria dados | tarefa, nota, projecto, checklist | conforme Definições (omissão: não) |
| Altera dados | concluir tarefa, mudar estado, executar automação | conforme Definições (omissão: sim) |
| Destrutiva | eliminar tarefa/projecto, arquivar | **sempre**, com descrição do que muda |
| Proposta pela IA | qualquer escrita | **sempre** |

Confirma-se por voz («sim» / «não») ou com os botões. Uma acção pendente expira ao fim de 30 minutos.

## Testes (critérios de aceitação)

✅ automatizado · 🔧 verificado com componentes reais sem microfone · ⏳ requer acção/hardware

| # | Critério | Estado | Onde |
|---|---|---|---|
| 1 | Navegação entre cards holográficos | ✅ | `assistant.test.tsx` (links «Abrir …») |
| 2 | Dados reais nos painéis | ✅🔧 | `assistant.test.tsx`; captura com dados de desenvolvimento |
| 3 | Activação manual | ✅ | `test_push_to_talk_uses_microphone_temporarily`, teste do botão |
| 4 | Activação por «UAJI» | ✅🔧 | `test_wake_word_then_voice_command_creates_task`; `python -m uanji.voice.selftest` |
| 5 | Estados de escuta e processamento | ✅ | testes de serviço; núcleo com 10 estados |
| 6 | Reconhecimento de uma pergunta por voz | 🔧 | auto-teste: Vosk transcreve correctamente fala sintetizada |
| 7 | Resposta escrita e falada | ✅🔧 | testes com TTS simulado; `say` real executado com Joana e Eddy |
| 8 | Selecção de voz disponível | ✅🔧 | catálogo real + teste de interface |
| 9 | Forma de tratamento | ✅ | `test_persona_settings_validation_and_persistence` |
| 10 | Criação real de tarefa por comando | ✅🔧 | API + auto-teste por voz |
| 11 | Consulta de projectos e tarefas | ✅ | `test_queries_use_real_data_and_never_invent` |
| 12 | Relatório com dados reais | ✅ | idem; secções separadas |
| 13 | Interromper a fala | ✅ | `test_stop_and_resume_speech`, `test_real_speaker…` |
| 14 | Texto com voz desactivada | ✅ | `test_listening_off_keeps_microphone_closed` |
| 15 | Sem Internet | ✅ | `test_unknown_without_ai_and_ai_errors` (local continua a funcionar) |
| 16 | Permissão de microfone negada | ✅ | `test_errors_permission_stt_and_tts` |
| 17 | Erros de STT, TTS e IA | ✅ | idem + teste de IA sem ligação |
| 18 | Confirmação de operações destrutivas | ✅ | `test_destructive_requires_confirmation_by_voice` + interface |
| 19 | Persistência após reiniciar | ✅ | `test_persona_settings_validation_and_persistence` |
| 20 | Desempenho | 🔧 | medições acima |

**Por testar com o microfone real (requer a sua presença):** permissão do macOS na app instalada,
detecção de «UAJI» com a sua voz (depois de gravar amostras), taxa de falsas activações com ruído
ambiente, transcrição da sua pronúncia e ecos do altifalante.

### Como testar manualmente

1. Definições → Voz e personalidade: confirme «Modelo instalado» (senão, «Descarregar modelo»).
2. «Gravar amostra» três vezes, dizendo «UAJI» de cada vez; depois «Testar detecção».
3. Ligue «Escuta». Diga «UAJI» → ouve «Estou aqui. Em que posso ajudar?» → «Quais são as minhas
   tarefas prioritárias de hoje?».
4. «Cria uma tarefa para rever a autenticação do Q360» → confirme em Tarefas.
5. «Apaga a tarefa rever a autenticação» → ouve o pedido de confirmação → «sim».
6. «Faz o relatório do meu dia» → Esc a meio → «Retomar leitura» na página do Assistente.
7. Desligue a escuta e confirme «Microfone fechado» na barra superior.

Auto-teste sem microfone: `cd backend && .venv/bin/python -m uanji.voice.selftest`.
