# Guia do Jayth

Este guia descreve a versão instalada do Jayth: o que cada parte faz, onde fica e como se usa. Os nomes de
botões e menus são os que aparecem na interface (neste idioma). Os dados deste computador (versão, modelo ativo,
pastas, atalhos…) são adicionados à parte, obtidos do próprio app no momento da consulta.

## O que é o Jayth

O Jayth é um aplicativo de desktop para Windows, macOS e Linux que transforma um modelo de IA local (formato GGUF,
com llama.cpp) em um agente que trabalha no computador do usuário: programa, cria e edita arquivos, executa comandos,
usa outros programas, navega na web com seu próprio navegador e lê e cria documentos do Word, Excel, PowerPoint e
PDF. Tudo acontece no computador e funciona sem internet depois que o modelo é baixado. O usuário aprova cada ação
(ou dá carta branca no modo automático). Também é possível usar modelos por API (OpenAI, Claude, Gemini, Ollama…).
Criado por Ing. Jeison Tuiran. Software livre com licença GPL-3.0. Site: https://github.com/Json-Tuiran/jayth.ai

## A janela principal

- **Barra lateral (esquerda):** no topo, o botão ≡ para ocultá-la (Ctrl+Shift+S) e o seletor **Chat / Code**.
  Abaixo, **Nova conversa** (Ctrl+N), **Pesquisar nas suas conversas** (Ctrl+K) e o histórico agrupado por data
  (Hoje, Ontem, Últimos 7 dias…; clique em um grupo para recolhê-lo). Clique com o botão direito em uma conversa:
  **Renomear** ou **Excluir**. Lá embaixo, o botão do seu perfil (**Seu perfil e configurações**) e, quando há uma
  versão nova, o botão de atualização. Com a barra oculta, ela aparece ao passar o mouse pela borda esquerda.
- **Barra superior:** à esquerda, o estado do modelo (ex.: “● Pronto · local”). À direita: **Temporário**
  (chat temporário), o globo (**Navegador do Jayth**), **Layout dos painéis**, a pasta (abre a pasta de
  trabalho) e **⋯ Mais opções** (Renomear conversa, Abrir pasta de trabalho, Excluir conversa). No Jayth Code
  aparecem também os botões do **Explorador de arquivos** (Ctrl+B), do **Terminal** (Ctrl+`) e do **Painel do
  agente** (Ctrl+L).
- **Menu do seu perfil** (embaixo na barra lateral): Configurações, Personalização, Memória, Assistentes e habilidades,
  Tarefas agendadas, Modelos, Modelos por API…, Atalhos de teclado, Enviar feedback…, Relatar um erro…,
  Verificar atualizações, Sobre o Jayth e Sair.
- **Bandeja do sistema:** Mostrar, Pergunta rápida, Parar agente e Sair.

## A caixa de mensagem

- **Enter** envia; **Shift+Enter** insere uma quebra de linha. Ctrl+V cola uma imagem.
- Botão **+**: Anexar arquivos ou documentos…, Anexar imagem…, Anexar captura de tela e **Usar um assistente**.
- **Microfone:** ditar com a voz (a transcrição é feita no computador; o modelo de ditado é baixado na primeira vez).
- **Chip de permissões** (ex.: “Perguntar” ou “Automático”): muda o modo de permissão desta conversa.
- **Chip do modelo** (ex.: “Qwen3.8 27B · Baixo”): troca de modelo, o **Esforço** (quanto ele raciocina antes de
  responder: Baixo, Médio, Alto), baixa ou adiciona modelos, Gerenciar modelos…, Modelos por API… e **Motor**
  (ligar ou desligar o modelo).
- Se o modelo estiver desligado, acima da caixa aparece um aviso com **Ligar modelo** (pode ser fechado com o ×; ele
  volta se a situação mudar). Se você escrever com o modelo desligado, o Jayth o liga e envia a mensagem quando estiver
  pronto.
- Enquanto o agente trabalha, o botão de enviar vira **Parar**.

## Modos de permissão

São alterados no chip de permissões da caixa de mensagem (para essa conversa) ou em **Configurações › Agente e
permissões › Permissões padrão**. São cinco: Somente leitura, Planejar, Perguntar, Editar arquivos e Automático (a
lista exata com a descrição de cada um vem nos dados desta versão). Nos modos que perguntam, cada ação mostra
**Permitir** e **Negar**. As ações delicadas (excluir, instalar, `sudo`, mexer no sistema ou em caminhos protegidos)
sempre pedem permissão, inclusive no Automático. No **Planejar** o agente pesquisa e propõe um plano; com **Executar o
plano** ele o coloca em prática (ou **Continuar ajustando**). Para parar na hora o controle do mouse: levar o ponteiro
ao canto superior esquerdo da tela.

## O que aparece enquanto ele trabalha

- Antes de cada ação o agente diz em uma frase o que vai fazer. Cada ação é uma linha com seu ícone e uma
  animação enquanto é executada; ao clicar nela, o detalhe se expande (o comando exato, a alteração, o resultado).
- **Pensamento:** a linha “Pensou por…” se expande para mostrar o raciocínio.
- **Capturas:** quando ele verifica algo olhando a tela ou uma janela, a captura aparece no chat (clique para vê-la
  em tamanho grande).
- **Plano:** em tarefas longas, uma lista de tarefas fixa acima da caixa de mensagem (Plano · n de m).
- **Perguntas:** se precisar de uma informação, ele pergunta com opções; responde-se com um clique ou com **Outra
  resposta…**.
- Os arquivos que o agente cria ou altera podem ser abertos a partir do chat (caminhos como links) e os comandos que o
  usuário deve executar aparecem com os botões **Copiar** e **Executar**.

## Ações sobre as respostas

Abaixo de cada resposta: **Copiar resposta**, **Ler em voz alta**, **Gerar resposta novamente** e **Relatar um problema com esta resposta**; à direita, os tokens que ele escreveu e a
velocidade. Se a resposta alterou arquivos, aparece abaixo o cartão **Alterou 2 arquivos** com cada arquivo, as linhas adicionadas
e removidas e uma nota (“novo”, “para a Lixeira”, “movido para …”): um clique abre o arquivo e o botão dele o volta a como estava
antes dessa resposta; com dois ou mais, **Desfazer tudo**. Cada ação que altera arquivos também tem seu próprio botão para
desfazer só essa alteração. Quando o agente usou ferramentas, a linha “Trabalhou por 3 min 12 s” separa o que ele fez da resposta.

## Enquanto trabalha: escrever para ele, permissões e avisos

- **Escrever sem pará-lo:** enquanto ele trabalha, dá para escrever e enviar (Enter ou o botão de enviar que aparece ao
  lado de **Parar**). A mensagem fica na fila acima da caixa de texto (com × para tirá-la) e o agente a vê no próximo
  passo; no chat ela aparece com a nota “Você escreveu isto enquanto ele trabalhava; ele viu aqui”. Se ele for parado antes, o texto volta para a caixa.
- **Passos agrupados:** o que ele pensa entre as ações (“Pensou por um momento”) fica dentro do grupo de ações; ao terminar, o grupo
  se recolhe em uma linha que se abre com um clique. No topo, o status mostra há quanto tempo ele está trabalhando
  (“Trabalhando · local · 1:12”).
- **Permissões:** além de **Permitir** e **Negar**, o campo “Ou diga o que fazer em vez disso e pressione Enter…” nega a ação e passa a instrução ao agente; abaixo
  da ação fica “Você pediu: “…””. “Sempre “…” aqui” não é oferecido em ações delicadas nem em ações em contas conectadas: essas são
  confirmadas toda vez.
- **Plano:** ao clicar em **Executar o plano**, o chat mostra a marca “Você aprovou o plano: ele é executado passo a passo”.
- **Controle do computador:** enquanto ele usa o mouse e o teclado, um aviso no topo da tela tem **Pausar** (o agente
  espera e o usuário pode usar o mouse; depois, **Continuar**) e **Parar**. Se o agente for clicar onde está o aviso, o
  aviso sai da frente. Também para levando o ponteiro ao canto superior esquerdo.
- **Avisos fora da janela:** se ele espera uma permissão ou uma resposta com o Jayth em segundo plano, o ícone da barra
  de tarefas pisca e aparece um aviso; se uma tarefa de mais de 15 segundos termina enquanto o usuário olha outra coisa,
  ele também avisa (clicar no aviso abre essa conversa).

## Memória da conversa (contexto)

Ao lado do microfone da caixa de mensagem, um anel mostra quanto da memória do modelo a conversa ocupa: na cor de
destaque se há espaço, âmbar a partir de 70 % (com a porcentagem) e vermelho a partir de 85 %. Aos 70 % o Jayth recorta
as saídas antigas das ferramentas (mantém o começo; as três últimas ficam inteiras). Se não bastar, aos 85 % o modelo
resume a parte antiga: o que veio antes da última mensagem do usuário ou, em uma única tarefa muito longa, os primeiros
passos (os últimos ficam como estão). O tamanho do resumo se adapta à memória do modelo. Ao clicar no anel: quanto
ocupa, o que o Jayth vai fazer, **Resumir agora** e **Começar uma conversa nova**. O aviso deixado pelo resumo tem **Ver o resumo**. Em
computadores sem placa de vídeo, resumir pode levar alguns minutos.

## Ações sobre as suas mensagens

Ao passar o mouse sobre uma mensagem sua: **Copiar mensagem**, **Editar e reenviar** (a edição é feita na própria
mensagem; Ctrl+Enter envia, Esc cancela), **Tentar novamente a partir daqui** e **⋯ Mais ações**: **Voltar a este
ponto** (remove essa mensagem e o que veio depois e deixa o texto na caixa) e **Nova conversa a partir daqui** (copia
a conversa até esse ponto; a original não muda). Se depois dessa mensagem o agente alterou arquivos, o Jayth pergunta
se deve **Desfazer essas alterações** ou **Manter os arquivos**. Não é possível voltar a uma mensagem que já ficou
dentro do resumo de uma conversa muito longa. É preciso esperar o agente terminar (ou pará-lo).

## Conversas

- São salvas sozinhas no histórico. **Pesquisar nas suas conversas** (Ctrl+K) pesquisa em títulos e mensagens.
- O título é definido pelo modelo após a primeira resposta; muda-se com **Renomear**.
- **Chat temporário** (botão **Temporário** da barra superior): não é salvo no histórico e não usa nem altera a
  memória.
- Os erros do chat (ex.: “Não consigo conectar ao modelo”) trazem **Tentar novamente** e **Remover este aviso**.
- Exportar todas para Markdown ou apagá-las: **Configurações › Dados e privacidade**.
- Quando uma conversa fica muito longa, o Jayth resume a parte antiga para que o modelo não a esqueça.

## Jayth Code (projetos)

- Entra-se com **Code** na barra lateral (Ctrl+2; Ctrl+1 volta ao Chat). **Novo projeto** ou **Abrir pasta…**.
  Os projetos aparecem na seção **Projetos** da barra lateral, cada um com suas conversas (clique com o botão direito:
  **Editar projeto…** para o nome, a pasta e as **instruções do projeto**; **Remover da lista**).
- **Explorador de arquivos** (Ctrl+B): ícones por tipo; os arquivos que o agente alterou têm um ponto verde. Clique
  com o botão direito: Abrir, Abrir com o app padrão, Novo arquivo…, Nova pasta…, Renomear, Copiar caminho, Copiar
  caminho relativo, Mover para a Lixeira. **Ir para um arquivo…** com Ctrl+P.
- **Editor:** abas (Ctrl+S salva, Ctrl+W fecha). Markdown, HTML, SVG e CSV abrem em **Visualização** e é preciso
  mudar para **Código** para editar. Word, Excel, PowerPoint e PDF aparecem em modo de leitura; as imagens, com zoom.
  **Abrir com o app padrão** abre o arquivo com o app do sistema. **Quebrar linhas** (Alt+Z) para as linhas longas.
- **Salvar automaticamente (salvamento automático):** por padrão salva após 1 segundo sem digitar. Muda-se em
  **Configurações › Geral › Editor do Jayth Code** (também ao trocar de aba ou de janela, ou desativado: salvar com
  Ctrl+S). Uma aba com “●” tem alterações não salvas; com “⚠”, não foi possível salvar (o motivo aparece ao passar o
  mouse).
- **Terminal** (Ctrl+`): o do sistema (PowerShell no Windows, zsh/bash no macOS e no Linux), dentro da pasta do
  projeto; ↑ ↓ percorre o histórico. Para comandos, não para programas interativos.
- **Painel do agente** (Ctrl+L): o chat do projeto; o agente trabalha dentro da pasta do projeto e lê as
  regras de AGENTS.md, JAYTH.md ou CLAUDE.md, se existirem.
- **Layout dos painéis** (barra superior): mostrar ou ocultar painéis, agente à esquerda ou à direita,
  terminal abaixo ou à direita do editor e **Modo foco (só o editor)** (Ctrl+Shift+M). Os divisores podem ser
  arrastados; clique duplo em um deles recolhe o painel ao lado. Tudo é lembrado.

## Navegador do Jayth

Botão do globo na barra superior. O usuário pode navegar nele ou pedir ao agente que use um site (pesquisar dentro
de um site, preencher formulários, páginas com JavaScript). O agente o controla à vista, com seu próprio ponteiro e um
brilho nas bordas enquanto tem o controle; o usuário pode intervir quando quiser. As senhas são sempre digitadas pelo
usuário, e o agente pede confirmação antes de comprar, pagar, publicar ou enviar dados pessoais.

Na barra dele: voltar, avançar, recarregar (ou parar enquanto carrega), o endereço (ou o que se quiser pesquisar),
**Pesquisar na página** (Ctrl+F), abrir a página no navegador do sistema e um menu com **Ampliar** e **Reduzir**
(Ctrl++ e Ctrl+-), **Copiar o endereço**, **Salvar a página como PDF** (Ctrl+P; vai para Downloads) e **Limpar os
dados do navegador** (cookies, logins e cache). O botão direito oferece as opções próprias de links, imagens e
texto. As páginas são pedidas no idioma da interface. Ao abrir o navegador, os outros painéis encolhem e, ao
fechá-lo, recuperam a largura.

## Tela (canvas)

Para páginas web, documentos longos, diagramas SVG ou programas que o usuário queira ver: o agente os mostra em um
painel ao lado do chat (“Ver na tela”), com visualização e código, versões (v1 de n) e opção de salvá-los.

## Imagens

O agente pode criar imagens novas (fotos, ilustrações, logotipos, ícones, fundos, capas) no próprio computador: quando
você pede ou quando uma tarefa precisa (ilustrar um site, uma apresentação ou um documento). Também modifica uma imagem
que você já tem (com FLUX.2 [klein]). Enquanto cria, mostra o passo em que está, o tempo que falta e uma prévia; ao
terminar, a imagem aparece grande no chat com **Abrir** e **Mostrar na pasta**. Ela é salva na pasta “imagens” da
pasta de trabalho (ou do projeto), ou na que for escolhida nas Configurações.

- Funciona sem internet nem serviços externos, com stable-diffusion.cpp (MIT) e um modelo de imagem de licença livre
  (Apache-2.0 ou MIT): **FLUX.2 [klein] 4B** (versátil e com texto dentro da imagem, o recomendado com placa de
  vídeo), **Z-Image Turbo** (mais realista, melhor com placa de vídeo) ou **Segmind Vega RT** (o mais rápido sem
  placa de vídeo, em 4 passos, com menos detalhe). No “Automático”, o Jayth escolhe conforme o
  computador. Sem placa de vídeo, o FLUX.2 leva cerca de 11 minutos por imagem (medido num notebook com um i5 de 4 núcleos).
- Na primeira vez é preciso instalá-lo (cerca de 5 GB, uma única vez): com **Instalar** no cartão que aparece no chat
  quando o agente precisa (depois, **Continuar**), ou em **Configurações › Imagens**. Dá para ver o progresso,
  cancelar, e o download continua se for interrompido. **Remover** apaga os arquivos.
- Tempo: com placa de vídeo, menos de um minuto por imagem; sem ela, vários minutos (por isso, sem placa de vídeo as
  imagens são criadas em 512 px). Muda-se em Configurações › Imagens › “Tamanho das imagens”.
- Só é usado se o modelo de texto ativo não cria imagens sozinho (hoje nenhum dos que rodam no llama.cpp faz isso).
  Desativa-se com “Permitir que o agente crie imagens”.
- Cada imagem é uma ação de escrita: conforme o modo de permissão, é aprovada antes de ser criada e pode ser desfeita.
- Para gráficos de dados o agente usa Python, e para diagramas, SVG na tela.

## Conhecimento

Em **Configurações › Conhecimento** você escolhe pastas (notas, documentos, projetos) e o agente pesquisa nelas pelo
significado, não só por palavras exatas (“quanto custou consertar o carro?” encontra a nota da nota fiscal do carro),
sem precisar lê-las inteiras: ideal com modelos locais, que têm pouca memória de conversa. Ele faz isso com um
buscador pequeno que roda no computador (Qwen3-Embedding 0.6B, 640 MB, baixado uma vez) e entende espanhol, inglês,
português e muitos outros idiomas. Aceita texto, código, Markdown, Word, PDF, PowerPoint e Excel.

- **Busca por significado:** **Instalar** (uma vez).
- **Pastas de conhecimento:** **Adicionar pasta…** e **Remover**.
- **Índice:** quantos arquivos e fragmentos tem e quando foi atualizado; **Atualizar o índice** (só relê o que é novo
  ou mudou) e “Atualizar o índice ao abrir o Jayth”.
- O agente o usa só quando precisa (p. ex. “segundo as minhas notas…”) e cita de qual arquivo sai cada dado.

## Controle do computador e outros programas

O agente pode abrir programas e arquivos, ler os botões e campos de qualquer janela (acessibilidade do sistema),
clicar, arrastar, digitar, pressionar atalhos, gerenciar janelas, usar a área de transferência e fazer capturas da
tela ou de uma janela. Enquanto ele controla, aparecem um brilho nas bordas da tela e o ponteiro dele. Ativa-se ou
desativa-se em **Configurações › Ferramentas › Permitir o controle do computador**. No macOS é preciso dar ao Jayth as
permissões de **Gravação de Tela** e **Acessibilidade** (Ajustes do Sistema › Privacidade e Segurança). No Linux
funciona em sessões X11 (no Wayland o controle global é limitado); para listar janelas é necessário o `wmctrl`.

## Modelos

- **Modelos** (menu do perfil, ou Configurações › Modelos › Gerenciar modelos…): lista dos modelos instalados com
  tipo, variante e tamanho. **Usar este**, **Adicionar modelo…**, **Localizar…** (se você moveu o arquivo),
  **Pesquisar em uma pasta…**, **Abrir pasta**, **Remover da lista** e **Excluir arquivos…**.
- **Adicionar um modelo** (assistente): catálogo de modelos abertos do Hugging Face marcados conforme caibam no
  computador (Agente = usa ferramentas; Visão = entende imagens; Raciocina = pensa antes de responder), um repositório
  digitado manualmente (usuário/Modelo-GGUF), um arquivo .gguf próprio ou uma pasta com o modelo original
  (config.json + .safetensors), que o Jayth converte para GGUF no computador. Escolhe-se a quantização (a recomendada
  vem marcada) e, se existir, a **visão** para que o modelo veja imagens e capturas.
- **Modelos por API…**: OpenAI, Claude, Gemini, Ollama, LM Studio ou outro servidor compatível com OpenAI. Também em
  **Configurações › Modelos › Provedor** (URL, nome do modelo e chave). Com um modelo por API, o Jayth pergunta ao
  serviço quanto contexto e quanta saída esse modelo aceita e usa esses valores (com um teto de 200.000 tokens por
  passo para conter o gasto), se adapta sozinho se o serviço rejeitar algum parâmetro, permite turnos mais longos
  (120 passos) e oferece ao agente **ajudantes**: subtarefas feitas por outra cópia do modelo, das quais só volta o
  relatório. O agente decide o que cada ajudante pode fazer (só ler e pesquisar, também alterar arquivos de algumas
  pastas específicas, ou ainda executar comandos) e responde por isso: o que o ajudante faz aparece no chat, pode
  ser desfeito e, se precisar de uma permissão do usuário, ela é negada e o próprio agente faz. A delegação pede
  permissão ao usuário como a ação equivalente pediria. O mesmo diálogo mostra o **consumo** de cada serviço salvo:
  solicitações, tokens e custo aproximado de hoje, dos últimos 30 dias e no total, por modelo; os limites da conta
  segundo a última resposta do serviço; o saldo, se o serviço informar (OpenRouter, DeepSeek); e avisa sobre os
  modelos novos ou retirados. **Consumo oficial** abre a página do serviço com o valor e o plano reais (o Jayth só
  conta o que foi enviado a partir deste computador) e **Preço de um modelo…** serve para informar o preço de um
  modelo que o Jayth não conhece. No chat, cada turno com um modelo por API termina dizendo quantos tokens gastou e
  o custo aproximado. Esses serviços pensam sem mostrar e entregam cada ação de uma vez, então o chat pode passar
  um tempo dizendo que o serviço está preparando a resposta; se uma solicitação travar, o Jayth a interrompe e pede
  ao modelo que continue.
- **Ligar ou desligar o modelo:** chip do modelo › **Motor**, ou o botão **Ligar modelo** do aviso. Ligado, ele
  ocupa memória e responde na hora; desligado, libera a memória.
- Os downloads mostram porcentagem, velocidade e tempo, continuam de onde pararam se forem interrompidos e são
  verificados com SHA-256.
- Se for publicada uma versão nova de um dos seus modelos, o Jayth avisa (desativa-se em Configurações › Sobre ›
  Novidades).

## Motor e desempenho

O Jayth baixa a versão oficial do llama.cpp adequada ao computador: Metal em Mac com Apple Silicon, CUDA para NVIDIA,
Vulkan para AMD ou Intel Arc, ou CPU. Em **Configurações › Desempenho**: **Trocar ou atualizar o motor…**,
**Pré-aquecer ao ligar o modelo**, **Memória da conversa (contexto)** (por padrão **Automático**: todo o contexto que
o modelo suporta de fábrica, reduzido se a memória dele não couber no computador; com **Contexto comprimido** cabe o
dobro ou mais), **Desligar o modelo se não for usado por**, e em
**Configurações do motor**: Threads da CPU, Threads ao ler (automático: sem placa de vídeo lê com todos os threads do processador), Camadas na GPU (o automático divide o modelo entre GPU e RAM), Tamanho do
lote, Contexto comprimido, Flash attention, Aceleração ao escrever, mmap, travar na RAM e a porta local. As alterações do motor são aplicadas
ao reiniciar o modelo (**Reiniciar modelo**). O log do motor fica em **Configurações › Log do modelo**.

- **Otimizar para este computador** (Configurações › Desempenho): em vez de estimar, mede de verdade com o modelo
  ativo (alguns minutos, com o modelo desligado enquanto isso): testa threads e flash attention com o llama-bench e a
  “Aceleração ao escrever” (decodificação especulativa: **MTP**, para modelos que trazem essas camadas, como Qwen 3.5 e
  3.8, e **n-gramas**, que acelera ao reescrever código ou texto), e fica com o mais rápido. O resultado aparece embaixo
  (“lê … tok/s · escreve … tok/s”). A “Aceleração ao escrever” também pode ser escolhida à mão em Configurações do motor.
- **Memória:** ao ligar o modelo, o Jayth avisa se ele não cabe no computador (vai ficar muito lento e é melhor uma
  variante menor) ou se naquele momento outros programas ocupam a memória. A memória que o llama.cpp guarda de conversas
  anteriores se ajusta sozinha ao que sobra, para não tirá-la do modelo.

## Configurações

Abrem-se pelo menu do perfil (**Configurações**). As alterações são salvas sozinhas. Páginas e opções (com o nome
exato):
- **Geral:** “Idioma da interface”, “Tema”, “Tamanho do texto”, “Animações (aparição de mensagens, barra
  lateral, avisos)”, “Barra de título integrada à janela” (só Windows).
  - **Editor do Jayth Code:** “Salvar arquivos automaticamente”.
  - **Inicialização e janela:** abrir o Jayth ao iniciar o sistema (minimizado na bandeja), “Ligar o modelo ao abrir
    o Jayth”, “Ao fechar a janela, continuar funcionando na bandeja do sistema”, “Avisar quando o agente precisar da
    minha aprovação”, “Atalho da janela rápida”.
- **Personalização:** “Como você quer ser chamado?”, “O que o Jayth deveria saber sobre você?”, “Como você quer que
  ele responda?”, “Idioma das respostas”, “Instruções adicionais para o agente”.
  - **Voz:** “Precisão do ditado”, “Idioma do ditado”.
  - **Memória:** “Usar a memória (lembrar coisas entre conversas)”, a lista de lembranças (adicionar, editar ou
    apagar) e **Apagar toda a memória**.
- **Modelos:** o modelo ativo, **Gerenciar modelos…**, **Adicionar modelo…**, **Assistente de configuração…** e “Pasta
  onde os modelos são baixados”.
  - **Provedor:** “Qual motor o agente usa?” (local ou servidor externo), “URL do servidor externo (termina em /v1)”,
    “Nome do modelo nesse servidor”, “Chave de API (se o servidor pedir)” e **Testar conexão**.
- **Geração:** “Pensar a fundo por padrão (respostas melhores, mais lento)”, “Parâmetros de amostragem” (recomendados
  para o modelo ativo ou personalizados), “Temperatura”, “Tamanho máximo de cada resposta (tokens)”.
  - **Amostragem avançada:** “Top-p”, “Top-k”, “Min-p”, “Penalidade de repetição”, “Semente” e **Restaurar valores
    recomendados**.
- **Desempenho:** **Trocar ou atualizar o motor…**, “Pré-aquecer ao ligar o modelo”, “Memória da conversa
  (contexto)”, “Desligar o modelo se não for usado por”.
  - **Configurações do motor:** “Threads da CPU”, “Threads ao ler”, “Camadas na GPU”, “Tamanho do lote”, “Contexto comprimido”, “Flash
    attention”, “Carregar o modelo com mmap (inicialização mais rápida)”, “Travar o modelo na RAM (evita que o sistema
    o mova para o disco)”, “Porta local do motor”.
  - **Downloads:** “Conexões simultâneas ao baixar modelos”.
- **Agente e permissões:** “Permissões padrão”, “Pasta de trabalho do modo Chat”, “Comandos permitidos sem
  perguntar”.
  - **Limites:** “Máximo de passos por tarefa”, “Tempo máximo de cada comando”, “Máximo de texto que o modelo recebe
    de cada ação”, “Enviar capturas e imagens ao modelo (se ele tiver visão)”, “Imagens recentes que ele lembra”.
- **Ferramentas:** “Permitir o acesso à internet (pesquisar, ler páginas e baixar)”, “Permitir o controle do
  computador (mouse, teclado, capturas)”, “Ferramentas carregadas” (por padrão, só as que cada tarefa precisa: o
  agente tem as básicas à mão e ativa os outros grupos —web, navegador, controle do PC, documentos, Python, imagens,
  agenda e cada conector— quando precisa; assim o modelo local tem mais memória e responde antes).
  - **Ferramentas disponíveis:** cada ferramenta do agente pode ser desligada separadamente.
  - **Pesquisa na web:** “Buscador” (automático com DuckDuckGo e Bing, sem chave; Brave Search ou SearXNG), “Chave do Brave
    Search”, “URL do SearXNG”.
  - **Serviços com a sua conta:** cartões para conectar serviços online (**Conectar**, **Desconectar**, **Configurar
    Google…**).
  - **Conectores MCP:** predefinições, adicionar (**Adicionar e testar**), testar e remover conectores.
- **Conhecimento:** busca por significado (**Instalar**), pastas (**Adicionar pasta…**, **Remover**), índice
  (**Atualizar o índice**) e “Atualizar o índice ao abrir o Jayth”.
- **Imagens:** “Permitir que o agente crie imagens”.
  - **Modelo de imagem:** “Modelo escolhido” (Automático, FLUX.2 [klein] 4B, Z-Image Turbo ou Segmind Vega RT), o seu estado e **Instalar**,
    **Cancelar** ou **Remover**.
  - **Imagens criadas:** “Tamanho das imagens” (Automático, 512, 768 ou 1024 px) e “Pasta onde são salvas”.
- **Dados e privacidade:** a pasta de dados (**Abrir pasta**).
  - **Conversas:** **Exportar conversas (Markdown)…**, liberar espaço de imagens não usadas e apagar todas as
    conversas.
- **Log do modelo:** o log do motor llama.cpp (para diagnóstico) e **Atualizar**.
- **Atalhos de teclado:** a lista de atalhos.
- **Sobre:** versão, autor e licença (**Ver a licença**, **Política de marca**), **Verificar atualizações**,
  **Abrir no GitHub**.
  - **Novidades:** “Avisar quando houver uma nova versão do Jayth”, “Baixar as atualizações em segundo plano e
    instalá-las ao fechar o Jayth”, “Avisar quando sair uma nova versão dos meus modelos”.
  - **Feedback:** **Relatar um erro…** e **Sugerir uma melhoria…**.

## Personalização e memória

Em **Personalização** você diz ao agente como deve chamar você, o que saber sobre você, como responder (estilo), em
que idioma responder (Automático = o idioma da sua mensagem) e instruções adicionais. A **memória** guarda
preferências duradouras entre conversas (o agente as salva quando você as diz, ex.: “uso pnpm”); pode ser revisada,
editada ou apagada em Personalização › Memória e pode ser desligada. O chat temporário não a usa.

## Assistentes e habilidades

Menu do perfil › **Assistentes e habilidades**. Um **assistente** é um agente com instruções e arquivos de referência
próprios (ex.: “Revisor de estilo”); escolhe-se com **+ › Usar um assistente** na caixa de mensagem. Uma
**habilidade** é um procedimento que o agente usa quando ele se encaixa na tarefa (ex.: “Redigir relatórios executivos
e entregá-los em Word”); são criadas, importadas, ativadas ou desativadas na aba Habilidades (**Adicionar exemplos**
traz algumas de amostra).

## Tarefas agendadas

Menu do perfil › **Tarefas agendadas**. Uma tarefa é um encargo que o agente faz sozinho no horário marcado (Uma vez,
Todos os dias, De segunda a sexta, Toda semana nos dias escolhidos ou Em intervalos) e avisa ao terminar: **Nova
tarefa**, nome, o que deve fazer, quando, como age (permissões), **Executar agora** e **Ver último resultado**. As
tarefas são executadas enquanto o Jayth estiver aberto (inclusive na bandeja). O agente também pode agendá-las se você
pedir.

## Janela rápida

Uma barrinha para perguntar ao Jayth a partir de qualquer programa: atalho **Ctrl+Alt+J** (muda-se ou desativa-se em
Configurações › Geral › Atalho da janela rápida) ou **Pergunta rápida** na bandeja. **Com captura** anexa uma imagem
do que estava na tela (Ctrl+S). Enter envia, Esc fecha.

## Conectores MCP e pesquisa na web

- **Conectores MCP** (Configurações › Ferramentas): ampliam as ferramentas do agente com o padrão Model Context
  Protocol (arquivos, memória, navegador Playwright, Git, Fetch, GitHub…). Há predefinições que preenchem o
  formulário; podem ser um programa do computador (comando e argumentos; muitos precisam de Node.js ou uv) ou um
  serviço remoto (endereço e chave). **Adicionar e testar** os conecta; se o serviço pedir login, a página dele se
  abre (depois, **Entrar** ou **Sair** na linha dele).
- **Serviços com a sua conta** (Configurações › Ferramentas): tudo é opcional; o Jayth funciona localmente e sem
  internet. Há cartões para Higgsfield (imagens e vídeo com IA na nuvem, com os seus créditos), Notion, Canva, Gmail,
  Google Drive, Google Calendar, Linear, Jira e Confluence, e Hugging Face (sem conta). **Conectar** abre a página do
  serviço no navegador: o usuário entra lá e autoriza; o Jayth nunca vê a senha e guarda a permissão criptografada no
  computador (ela se renova sozinha). **Desconectar** a esquece. Gmail, Drive e Calendar pedem antes **Configurar
  Google…**: criar uma vez um “ID do cliente OAuth” do tipo “App para computador” no Google Cloud (com as APIs de MCP
  ativadas e o e-mail como usuário de teste) e colar o ID e a chave secreta; serve para os três.
- Se uma tarefa precisar, o agente pode propor conectar um serviço: o cartão dele aparece no chat com **Conectar** e,
  ao terminar, **Continuar**. O que mudar algo na conta (enviar, publicar, gastar créditos) sempre pede aprovação,
  inclusive no modo Automático; ler, não.
- **Pesquisa na web:** funciona sem configurar nada: DuckDuckGo e, se ele pedir verificação (o Jayth não a contorna), o Bing pelo motor do navegador integrado, sem exibi-lo. A Wikipedia fica como último recurso. Uma chave do Brave Search ou uma instância própria do SearXNG são opcionais.

## Idioma da interface

O Jayth está em espanhol, inglês, português (Brasil), francês, alemão, italiano,
japonês e chinês simplificado. Na primeira vez, usa o idioma do
sistema (inglês, se não for nenhum destes); muda-se em
**Configurações › Geral › Idioma da interface** e o Jayth se oferece para reiniciar e aplicá-lo. O idioma em que o
agente responde é outra coisa: por padrão, o da mensagem do usuário (Configurações › Personalização › Idioma das
respostas).

## Atualizações

Quando há uma versão nova, o Jayth a baixa em segundo plano (o botão da barra lateral mostra “Baixando
atualização… %”) sem interromper nada. Ao terminar, o botão passa a **Reiniciar para atualizar**: ao clicar nele, o
Jayth fecha, a versão nova é instalada (com uma janelinha “Atualizando…”) e ele abre de novo. Se você não clicar, ela
é instalada sozinha ao fechar o Jayth. Ao abrir a versão nova, aparece um aviso com link para as **Novidades**. É
possível verificar manualmente no menu do perfil › **Verificar atualizações** e desativar o download automático em
Configurações › Sobre › Novidades. Conversas, configurações e modelos são mantidos ao atualizar.

## Onde tudo fica salvo

- **Configurações, conversas, motor e modelos:** Windows `%LOCALAPPDATA%\Jayth`, macOS `~/Library/Application
  Support/Jayth`, Linux `~/.local/share/jayth` (o caminho real deste computador vem nos dados desta versão).
- **Pasta de trabalho do modo Chat:** por padrão `Documentos/Jayth`; muda-se em Configurações › Agente e permissões.
- **Pasta de modelos:** muda-se em Configurações › Modelos. Os modelos de imagem ficam na subpasta `imagen`, e o motor
  de imagens, junto ao do llama.cpp (`runtime/imagen`).
- **Modo portátil:** um arquivo `portable.txt` junto ao programa salva tudo em `userdata/` ao lado dele (para um
  pendrive USB).
- **Privacidade:** tudo fica no computador; o Jayth não envia conversas nem arquivos a nenhum servidor. Ele só usa a
  internet para baixar modelos e motores, verificar atualizações e as ferramentas web que o usuário permitir (ou ao
  usar um modelo por API, que recebe as mensagens dessa conversa). Comentários e relatórios só saem do computador quando o usuário clica em **Enviar**.
- **Desinstalar:** Windows, Configurações › Aplicativos › Jayth › Desinstalar; macOS, arrastar o Jayth para a
  Lixeira; Linux, apagar o AppImage. Os dados e modelos não são apagados ao desinstalar.

## Feedback e ajuda

Menu do perfil › **Enviar feedback…** ou **Relatar um erro…** (também em Configurações › Sobre): o usuário
revisa o texto antes de enviá-lo. Abaixo de cada resposta, **Relatar um problema com esta resposta**. Com **Enviar**, o comentário chega diretamente e de forma privada à equipe do Jayth (não é publicado e não precisa de conta); **Publicar no GitHub** abre, em vez disso, uma issue pública no GitHub. Se o Jayth tiver um erro inesperado, ele o guarda no computador (sem caminhos pessoais) e oferece **Enviar relatório…**; nunca o envia sozinho. O
projeto está em https://github.com/Json-Tuiran/jayth.ai (downloads em Releases).

## Problemas frequentes

- **“O modelo está desligado” ou não responde:** clicar em **Ligar modelo** (ou escrever: o Jayth o liga sozinho). Se
  não iniciar, o motivo aparece no aviso e em Configurações › Log do modelo; costuma ser memória insuficiente:
  escolher uma quantização menor, reduzir a **Memória da conversa (contexto)** ou usar **Contexto comprimido**.
- **Está lento:** em computadores sem GPU os modelos grandes demoram; experimentar um modelo menor, reduzir o esforço
  para Baixo ou, com GPU NVIDIA, verificar se o motor é CUDA (Configurações › Desempenho › Trocar ou atualizar o
  motor…).
- **Não encontra o modelo (“Não encontro o arquivo…”):** clicar em **Procurar** ou, em Modelos, **Localizar…** ou
  **Pesquisar em uma pasta…**.
- **Não vê as imagens:** o modelo precisa de visão (projetor); ao adicioná-lo, marcar **Incluir visão**. Verificar
  Configurações › Agente e permissões › Enviar capturas e imagens ao modelo.
- **Não cria imagens ou falha ao criá-las:** instalar o gerador em Configurações › Imagens e verificar se “Permitir que
  o agente crie imagens” está marcado. Se faltar memória, escolher um tamanho menor ou FLUX.2 [klein] e fechar outros
  programas; os detalhes da última tentativa estão no arquivo `imagen.log` da pasta de dados.
- **Não consegue usar a internet ou o mouse:** revisar Configurações › Ferramentas (acesso à internet, controle do
  computador e a lista de ferramentas).
- **O Windows mostra “O Windows protegeu o computador”:** o instalador ainda não está assinado: Mais informações ›
  Executar assim mesmo. **macOS:** na primeira vez, clique com o botão direito no Jayth › Abrir.
- **O agente não deixa voltar a uma mensagem:** esperar que ele termine ou pará-lo; as mensagens já resumidas não podem
  ser rebobinadas (usar Nova conversa).
- **Uma aba do editor mostra ⚠:** não foi possível salvar (arquivo somente leitura ou pasta protegida); o motivo
  aparece ao passar o mouse sobre a aba.
