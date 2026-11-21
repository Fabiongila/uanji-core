# Segurança

## Modelo de ameaça

Aplicação pessoal, um utilizador, um computador. Protegemos contra: outras aplicações/páginas web locais a falar com o backend, fuga de segredos (base de dados, logs, backups, exportações, IA), execução de código arbitrário, corrupção/perda de dados e acções destrutivas acidentais. Não protegemos contra malware com privilégios do próprio utilizador.

## Comunicação frontend ↔ backend

- O backend escuta **apenas em 127.0.0.1**, numa porta aleatória escolhida pelo Tauri.
- Todos os pedidos `/api/*` exigem `Authorization: Bearer <token>`; o token tem 256 bits, é gerado por sessão pelo processo Rust e comparado em tempo constante. Sem `UANJI_TOKEN` o backend recusa iniciar.
- Middleware de **Host** rejeita pedidos com cabeçalho `Host` diferente de `127.0.0.1`/`localhost` (protecção contra DNS rebinding).
- **CORS** restrito às origens do Tauri e do Vite de desenvolvimento.
- Em desenvolvimento no browser o token é injectado pelo proxy do Vite (ficheiro `.dev-token`, `chmod 600`, ignorado pelo Git) e não entra no bundle.
- `/health` e `/docs` (esquema OpenAPI) são públicos em localhost; não expõem dados.

## Permissões Tauri

Capacidade única `default`: `core:default` + `notification:default`. O WebView **não** tem acesso a shell, sistema de ficheiros, processos ou HTTP arbitrário. O backend é lançado exclusivamente pelo código Rust. CSP restrita (`connect-src` apenas `self`, IPC e `127.0.0.1`). `freezePrototype` está **desligado**: congelar os protótipos fazia falhar uma dependência dos gráficos no WebView (ecrã vazio ao abrir a app); a protecção principal continua a ser a CSP sem scripts externos e as permissões mínimas.

## Segredos

- Valores no **macOS Keychain** (`keyring`, serviço `com.uanji.core`). A base de dados guarda só nome, serviço e os últimos 4 caracteres.
- Se o Keychain não estiver disponível, o cofre recusa gravar (HTTP 503) — não há alternativa insegura em produção. O `MemoryStore` existe só para testes e identifica-se como inseguro na interface.
- Leitura apenas por acção explícita («Copiar», regista no histórico sem o valor, limpa a área de transferência após 30 s) ou internamente por integrações configuradas.
- Logs com redacção automática (`token=`, `Authorization`, `api_key`, padrões `ghp_…`, `github_pat_…`, `sk-…`).
- Backups e exportações **não incluem** segredos.
- Não existe criptografia própria.

## Automações

Apenas acções internas tipadas e validadas (Pydantic). Sem `eval`, sem shell, sem acesso a ficheiros. Modelos `{{…}}` fazem substituição de texto a partir de um dicionário. Limites: 25 etapas, 30 s, 3 níveis de encadeamento, repetição apenas de falhas recuperáveis. Cada execução e etapa ficam registadas. Não há rollback automático — limitação explícita na interface.

## Assistente, voz e microfone

- O assistente funciona localmente sem IA; o fornecedor de IA é opcional e só recebe texto.
- Todas as operações passam por ferramentas tipadas (`assistant/tools.py`); sem SQL arbitrário, código gerado nem comandos de terminal.
- Acções destrutivas e escritas propostas pela IA exigem **sempre** confirmação, com descrição do que muda; o sucesso só é anunciado depois do *commit*.
- Microfone: fechado por omissão; aberto só com a escuta ligada (indicador permanente na barra superior) ou durante um pedido explícito. O áudio é processado em memória e nunca guardado nem enviado; só as amostras da palavra de activação gravadas pelo utilizador ficam na pasta de dados.
- Histórico de conversa (texto) com retenção configurável (0 = não guardar) e apagamento com confirmação.
- O modelo de reconhecimento só é descarregado por acção explícita, com verificação de caminhos no ZIP.

## Monitor de actividade e acções no sistema

- Monitor desligado por omissão; ao ligar, a interface explica o que é recolhido. Só nome da aplicação activa, tempo de inactividade (número), pasta do VS Code e, opcionalmente, título da janela e commits Git. Nunca teclas, conteúdo, capturas ou sites. Dados só locais, retenção configurável, apagamento com confirmação, aplicações excluídas.
- Acções no sistema por ferramentas tipadas (`system/macos.py`), sem shell para abrir apps/sites/pastas/volume (listas de argumentos fixas). Abrir pastas só dentro da pasta pessoal; sites só `http(s)` (o resto vira pesquisa).
- Comandos de terminal: desligados por omissão; com a opção ligada, cada comando exige confirmação explícita mostrando o comando exacto; tempo limite de 30 s; recusa `sudo`, formatação, `dd`, apagar raiz/pasta pessoal, desligar e bombas de processos. Esta lista não torna um comando seguro — a confirmação é a protecção principal.
- Mensagens por iniciativa respeitam horas de silêncio e não falam durante reuniões.

## Gatilhos externos e modelos próprios

- Webhooks em `POST /hooks/{id}`: sem token de sessão, mas com segredo por automação comparado em tempo constante; só o SHA-256 é guardado; o segredo é mostrado uma vez; corpo limitado a 64 KB; a protecção de `Host` mantém-se, por isso só aceita chamadas locais.
- Na app instalada o backend prefere a porta 48765, para o endereço dos webhooks não mudar; se estiver ocupada, usa outra.
- A acção «chamar webhook» envia dados para o endereço configurado na automação, que tem de ser escolhido pelo utilizador.
- Modelo próprio: `http` só para localhost; servidores remotos exigem `https`. Num servidor remoto, o texto dos pedidos e os dados consultados são enviados a esse serviço. As escritas propostas seguem a regra da IA: confirmação sempre.
- Abrir ficheiros pela Command Palette só funciona dentro das pastas de projectos configuradas.

## Assistente de IA

- Desligado por omissão; nenhum serviço pago é necessário.
- O modelo só actua através de ferramentas tipadas; escritas ficam **pendentes até confirmação** do utilizador.
- Resultados das ferramentas são enviados como `untrusted_data` e o prompt de sistema instrui o modelo a tratá-los como dados.
- Nenhuma ferramenta acede ao cofre; a chave da API é lida do Keychain apenas para a chamada.
- A interface distingue «Resposta gerada por IA» de «Dados consultados na aplicação».
- Limitação: o conteúdo consultado (notas, tarefas) é enviado ao fornecedor externo quando o assistente é usado.

## Dados e operações destrutivas

- Eliminações exigem confirmação (HTTP 428 + diálogo).
- Restauro/importação: validação (estrutura do ZIP, manifesto, SHA-256, `PRAGMA integrity_check`, revisão de esquema conhecida), confirmação e **backup de segurança automático** antes de substituir.
- Nomes de ficheiros de backup validados por expressão regular e confinados à pasta de backups (sem path traversal).
- Notas com controlo de revisão (HTTP 409 em conflito) e rascunho local para não perder conteúdo.
- Markdown renderizado sem HTML bruto (`react-markdown` por omissão).

## Limitações conhecidas

- Qualquer processo do mesmo utilizador que leia a memória/ambiente do backend pode obter o token da sessão.
- O cofre depende do Keychain de sessão iniciada; num computador novo, os segredos têm de ser reintroduzidos.
- A integração GitHub é só de leitura; tokens com permissões excessivas continuam a ser responsabilidade do utilizador (recomenda-se *fine-grained*, só leitura).
- Assinatura/notarização da aplicação macOS não está configurada (requer conta Apple Developer).
