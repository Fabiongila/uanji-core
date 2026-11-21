# Autonomia: iniciativa, actividade no computador, sistema e adaptação

## 1. O assistente toma a iniciativa

`backend/uanji/assistant/proactive.py` avalia regras a cada 30 s e fala sem esperar por um clique.
Com a escuta ligada, depois de uma pergunta («Quer que leia as prioridades?») o microfone fica a
ouvir a resposta durante 10 s, sem precisar de dizer «UAJI». «Sim» executa a oferta; «agora não»
dispensa-a. Também há botões na conversa.

| Regra | Quando | Oferta |
|---|---|---|
| Bom dia | primeira avaliação entre as 5h e as 13h | ler as prioridades |
| Bem-vindo de volta | regresso após ≥ 20 min ausente (monitor) | o que ficou pendente |
| Prazos | tarefa a vencer na próxima hora | marcar como concluída |
| Compromissos | evento nos próximos 10 min | — |
| Pausas | ≥ 90 min activo sem pausa (monitor) | — |
| Foco longo | sessão de foco com ≥ 50 min | terminar o foco |
| Mudanças de contexto | muitas trocas de aplicação em 15 min (monitor) | iniciar foco |
| Sugestões | ≥ 30 min a programar num projecto / numa pasta sem projecto | foco no projecto / criar projecto |
| Automações | execução falhada | — |
| Fim do dia | depois da hora da revisão diária | resumo do dia |

Limites (para ser presente sem ser intrusivo): intervalo mínimo entre mensagens (45/20/8 min
conforme a frequência escolhida; prazos e compromissos são excepção), horas de silêncio, nenhuma
fala durante reuniões (Zoom, Teams, FaceTime…), espera que a pessoa esteja ao computador, e cada
aviso é dado uma única vez (registado como notificação interna `proactive:<chave>`, por isso não se
repete depois de reiniciar). Cada regra pode ser desligada em Definições → Iniciativa do assistente.

## 2. Monitor de actividade (opcional, desligado por omissão)

`backend/uanji/activity/monitor.py`. Ao ligar, a interface explica o que é recolhido.

| Recolhido | Como | Permissão do macOS |
|---|---|---|
| Aplicação em primeiro plano | `CGWindowListCopyWindowInfo` + `NSRunningApplication` | nenhuma |
| Tempo sem teclado/rato (só o número) | `CGEventSourceSecondsSinceLastEventType` | nenhuma |
| Pasta aberta no VS Code | ficheiro de estado do próprio VS Code | nenhuma |
| Título da janela (opcional) | `kCGWindowName` | Gravação de ecrã |
| Commits do dia (opcional) | `git log` nas pastas indicadas | nenhuma |

**Não** recolhe teclas, conteúdo, capturas de ecrã nem sites visitados. Amostras iguais seguidas são
agrupadas em sessões (`activity_sessions`, migração 0004); a inactividade fecha a sessão e não conta.
Aplicações excluídas (gestores de palavras-passe por omissão) nunca são registadas. Retenção
configurável (30 dias) e apagamento total com confirmação. Medido neste Mac: ~6 ms por amostra.

As sessões são associadas a projectos pelo nome (ex.: pasta «Q360-Linha-Saude-backend» → projecto
«API Q360 Linha Saúde»). `activity/insights.py` calcula o resumo do dia e os padrões dos últimos 14
dias (hora média de início, horas mais intensas, aplicações mais usadas).

**Personalização:** o relatório do dia inclui o tempo no computador; o bom-dia compara a hora de
início com o hábito e sugere as horas mais intensas para a tarefa mais exigente; a IA (se configurada)
recebe um resumo de uma linha da actividade do dia; perguntas como «o que tenho estado a fazer?»,
«quanto tempo passei no Chrome?», «quais são os meus hábitos?», «que commits fiz hoje?».

## 3. Acções no sistema

`backend/uanji/system/macos.py`, exposto como ferramentas tipadas com nível de risco:

| Pedido (exemplos) | Ferramenta | Risco / confirmação |
|---|---|---|
| «abre o VS Code», «abre o Chrome» | `open_app` | sistema — sem confirmação (configurável) |
| «abre o site github.com», «pesquisa na web …» | `open_url` | sistema |
| «abre a pasta Documents/Projectos» | `open_path` (só dentro da pasta pessoal) | sistema |
| «volume a 30», «silencia» | `set_volume` | sistema |
| «como está a bateria?», «que aplicações estão abertas?» | `system_status`, `running_apps` | consulta |
| «fecha o Chrome» | `quit_app` (como ⌘Q; a app pode pedir para guardar) | altera — confirmação |
| «corre o comando ls -la» | `run_shell` | **desligado por omissão; confirmação sempre** |

Comandos de terminal: correm em zsh, na pasta pessoal, com 30 s de limite e saída truncada; são
sempre recusados `sudo`, formatação de discos, `dd`, apagar a raiz/pasta pessoal, desligar e bombas
de processos. A confirmação mostra o comando exacto. Pedidos interpretados pela IA nunca correm sem
confirmação.

## 4. Aparência e adaptação

- Temas (UANJI, Abismo, Âmbar, Alto contraste, Claro), cor de destaque (ciano, azul, âmbar,
  esmeralda, violeta), densidade, tamanho da interface (85–130 %), barra lateral à esquerda/direita.
  Implementado com variáveis CSS (sem custo de desempenho); pré-visualização imediata.
- Painel inicial: «Personalizar painel» para mover, redimensionar (pequeno/médio/grande/largura
  total) e esconder cards.
- **Disposição adaptativa:** a aplicação conta (localmente, com decaimento) as áreas que visita e
  ordena os cards por esse uso; alertas e tarefas atrasadas sobem sempre; o assistente fica entre os
  três primeiros.

## Testes

`backend/tests/test_autonomy.py` (11) e `frontend/src/__tests__/autonomy.test.tsx` (4). Verificado
também com a aplicação real neste Mac: o monitor registou a aplicação activa; o bom-dia foi
entregue sozinho 20 s depois do arranque; o tema claro e a página Actividade foram capturados.

**Por validar consigo:** a resposta por voz a uma pergunta da iniciativa (requer microfone), a
frequência adequada das mensagens no seu dia real, e a associação das suas pastas aos projectos.
