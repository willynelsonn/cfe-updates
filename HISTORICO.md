# Histórico do projeto FolhaWeb (Sistema de folha de pagamento)

Este arquivo resume as conversas em que o sistema foi construído e colocado para rodar, para que uma
conversa nova continue o trabalho sem perder contexto. O `README.md` é o manual de uso e instalação.

- **Repositório:** `willynelsonn/cfe-updates` (GitHub)
- **Branch com este arquivo atualizado:** `claude/gracious-bell-4jgktd`. A `main` tem todo o código
  (PRs #1 a #6 já mergeados), mas não tem este arquivo. O branch `claude/nifty-einstein-6lgypb` tem
  uma versão mais antiga dele.
- **O repositório é PÚBLICO.** Não coloque nele nomes ou dados de clientes e funcionários, senhas,
  certificados nem o banco de dados. O `.gitignore` já deixa de fora o `db.sqlite3`, o `.env`, os
  arquivos `.pfx`/`.p12`, `private_media/` e `backups/`.
- **Dono / usuário:** Willyson Oliveira. O sistema é para o departamento pessoal do escritório (o primo
  dele). Ele fala português e não é programador: as instruções devem ser simples, passo a passo, com
  comandos prontos para colar no PowerShell, pedindo print quando algo der errado.
  Ele trabalha no Windows, com Chrome. Ao fim de cada etapa de código, costuma pedir
  **"crie o PR e faça o merge"**.

---

## 0. Onde paramos (leia primeiro)

- O sistema **roda no PC dele** e abre no Chrome em `http://127.0.0.1:8000`. Confirmado em 11/11/2026.
- O banco do PC tem a **empresa de demonstração** "Padaria Pão Quente", com dados fictícios, e o
  usuário de teste `admin` (senha `admin`). O usuário real dele é `willysonoliveira`.
- **Próximo passo:** cadastrar a **primeira empresa real**, uma cliente do escritório. Ele abriu a tela
  *Nova empresa* (`/empresas/nova/`) e pediu para preenchê-la com os dados que estão na pasta dessa
  cliente, dentro de `C:\Users\Willyson Oliveira\OneDrive\Documentos\Clientes\CLIENTES DIVERSOS\`.
  O nome da pasta, que é o nome da cliente, ele informa na conversa. Não está registrado aqui porque o
  repositório é público.
  - Procurar na pasta o **cartão CNPJ** e documentos com RAT, FAP, FPAS e sindicato.
  - A pasta tem nome de pessoa: confirmar se ela tem **CNPJ** (MEI ou empresa individual). Se ela for
    empregadora **pessoa física** (doméstica), o FolhaWeb não atende; isso é o eSocial Doméstico.
- **Pergunta em aberto:** o certificado digital A1 que vai assinar os envios é **da própria empresa**
  ou **do escritório** (com procuração no e-CAC)? Isso define o campo "CNPJ/CPF do transmissor".
- As conversas na nuvem **não alcançam o PC dele** (`list_computer_folders` sempre vazio). Para ler a
  pasta da cliente e rodar comandos, a continuação deve ser numa conversa do Claude rodando **no PC
  dele** (veja a seção 6.4).

---

## 1. O que o sistema faz

Django 5.2, Python 3.12+ (desenvolvido e testado no 3.13), SQLite por padrão. O PostgreSQL é opcional,
via `FOLHA_DB_ENGINE=postgres`.

Apps:
- **`empresas`**:
  - várias empresas (escritório contábil), CNPJ (inclusive alfanumérico), Simples/Lucro, RAT/FAP, terceiros;
  - certificado A1 com senha cifrada pela `FOLHA_SECRET_KEY`;
  - middleware de empresa ativa (seletor no canto superior direito);
  - comandos `dados_demo`, `backup`, `preparar_servidor`, `servir` e `configurar_dominio`.
- **`pessoal`**: funcionários (dados completos para o S-2200), dependentes (IRRF e salário-família),
  cargos com CBO.
- **`folha`**:
  - rubricas (S-1010) e competências;
  - cálculo da folha (`servico.py`, `calculo.py`, `tabelas.py`);
  - férias, 13º, rescisão (`rescisao.py`), custos (`custo.py`), painel (`painel.py`);
  - conformidade legal (`conformidade.py`), guias (`guias.py`) e relatórios (`relatorios.py`).
- **`esocial`**:
  - geração dos XML (`xml_eventos.py`) e validação nos XSDs oficiais (`schemas/`);
  - assinatura XMLDSig (`assinatura.py`), SOAP de lote e consulta (`webservice.py`);
  - fila com dependências entre eventos (`servico.py`);
  - Integra Contador / SERPRO para o DARF (`integra_contador.py`).

Funcionalidades (detalhe na tabela do README):
- **eSocial S-1.3:**
  - eventos S-1000, S-1005, S-1010, S-1020, S-2200, S-2230, S-2299, S-1200, S-1210 e S-1299;
  - assinados e transmitidos em lote, com fila automática que respeita a ordem exigida;
  - o S-1210 segue o regime de caixa (mês do pagamento).
- **Cálculos 2026:**
  - INSS progressivo com teto de 8.475,55;
  - IRRF com a redução da Lei 15.270/2025;
  - salário-família de 67,54;
  - FGTS de 8% (2% para aprendiz).
- **Folha mensal:** horas extras 50% e 100%, DSR, adicional noturno, insalubridade, periculosidade,
  faltas, vale-transporte e lançamentos livres.
- **Férias (CLT arts. 130 a 145):**
  - médias de variáveis, 1/3 e abono;
  - divisão do gozo entre meses;
  - naturezas da NT 04/2025: 1015, 1016, 1017 e 9221;
  - o INSS é retido no recibo de férias e compensado na folha.
- **13º salário:** 1ª parcela na folha (natureza 5504), 2ª parcela com 5001/9214, S-1200 e S-1299 anuais.
- **Rescisão (TRCT):**
  - todos os motivos comuns;
  - aviso proporcional, arts. 479 e 480, multa do FGTS;
  - naturezas 6000 a 6007, 6129 e 9299.
- **Custos:** custo real por funcionário e simulador "quanto custa contratar".
- **Painel:**
  - indicadores e gráfico de 12 meses;
  - agenda de prazos e pendências legais;
  - status do eSocial.
- **Guias:**
  - prévia do DARF da DCTFWeb e da GFD do FGTS;
  - DARF em PDF pelo Integra Contador, que é opcional e pago;
  - o FGTS Digital não tem API pública.
- **Relatórios** (menu *Relatórios*, `folha/relatorios.py` + `templates/folha/relatorio*.html`):
  - 20 relatórios, todos com impressão/PDF e "Baixar para Excel" (CSV com `;`, vírgula decimal e UTF-8 com BOM);
  - Folha do mês: resumo por rubrica, folha analítica, relação de líquidos (banco/PIX), INSS, IRRF, FGTS, encargos e guias;
  - Anuais: ficha financeira, resumo anual, informe de rendimentos (conferência), 13º, férias do ano, rescisões do ano;
  - Controle: provisão de férias e 13º, férias vencidas/a vencer, contratos a vencer (e o link para Custos);
  - Pessoas: relação de funcionários, admissões e desligamentos, aniversariantes, dependentes;
  - para criar um relatório novo: escreva `fn(empresa, filtros) -> Relatorio` e registre em `RELATORIOS`.
- **Interface:**
  - navegação em pílulas; fontes Plus Jakarta Sans e Instrument Serif;
  - GSAP 3.13 + ScrollTrigger e Three.js r170 (só no login), em `static/vendor`;
  - 6 temas de cor (`data-cor`), com a ordem dos gráficos validada para daltonismo; o padrão é Grafite (`FOLHA_COR_PADRAO`);
  - modo claro/escuro;
  - a tag `{% estatico %}` acrescenta `?v=mtime` para o navegador não usar arquivo antigo do cache.
- **Segurança (modo servidor, `FOLHA_DEBUG=false`):**
  - `.env` carregado pelo `settings`;
  - WhiteNoise, cookies seguros, sessão de 8h, cabeçalhos de segurança;
  - bloqueio de login após 5 erros por 15 minutos, por usuário e por IP via `CF-Connecting-IP` (`config/seguranca.py`);
  - o login do admin passa pela mesma tela;
  - log em `folhaweb.log`.

---

## 2. O que já foi feito

### Conversa 1: construção do sistema (sessão na nuvem "Sistema de folha de pagamento")

Pedidos do usuário, em ordem:
1. Um site/app para **registrar funcionários, enviar ao eSocial, DCTFWeb, FGTS e controlar a folha
   completa**. O escritório usa o Domínio Sistemas no servidor (não foi inspecionado).
2. **13º salário e férias**, com **tudo automatizado**:
   - o cadastro vai sozinho ao eSocial;
   - um botão de apuração calcula e envia;
   - um botão gera as guias.

   Postura pedida: "analista sênior do Ministério do Trabalho" (sempre conforme a lei) e "engenheiro
   sênior" (site intuitivo, com todo botão dizendo para que serve).
3. **Rescisão**, **custo de cada funcionário para a empresa** e um **painel** de alto nível. Achou o
   primeiro layout "amador" e pediu redesenho.
4. Redesenho com animação (Three.js, GSAP, motion design) e **mais opções de cor**. Escolheu
   **Grafite** (preto e branco), que virou a padrão.
5. Automatizar os passos do PowerShell: daí veio o **`FolhaWeb.bat`** (dois cliques).
6. "Publica na internet": escolheu **hospedar no próprio servidor** com Cloudflare Tunnel. Daí vieram
   o `Servidor.bat`, o `InstalarNoServidor.bat` e o `ConfigurarDominio.bat`.
7. **"Todos os relatórios possíveis para a folha"**: central com 20 relatórios.
8. **Decisão final:** *"Quero rodar esse projeto dentro do meu PC, não na internet."* O uso é **local**,
   com o `FolhaWeb.bat`. A parte de internet está pronta, mas não está em uso.

No PC, nessa conversa:
- Clonou o projeto em `C:\Users\Willyson Oliveira\Documents\cfe-updates`. Python e Git já estavam
  instalados (a atualização do Git travou com processos "bash" abertos; foi cancelada, o Git funcionava).
- Rodou o `FolhaWeb.bat` com sucesso e criou o superusuário `willysonoliveira`.
- Depois disse que "não abriu o site"; a causa provável era a janela do `FolhaWeb.bat` fechada.
- No fim, a conversa escreveu a primeira versão deste arquivo no branch `claude/nifty-einstein-6lgypb`.

### Conversa 2: continuação em 11/11/2026 (sessão na nuvem)

1. Leu este histórico e trouxe o arquivo para o branch `claude/gracious-bell-4jgktd`.
2. Rodou os testes: **76 testes, todos passando** (Python 3.13).
3. **Confirmado que o sistema abre no PC:** o usuário mandou print do Painel no Chrome, em
   `http://127.0.0.1:8000`. Estava logado como `admin` ("Administrador") na Padaria Pão Quente, ou
   seja, os dados de demonstração (`dados_demo`) foram carregados. Foi orientado a usar o usuário
   `willysonoliveira` daqui em diante.
4. Ele abriu a tela **Nova empresa** e recebeu a orientação de preenchimento:

   | Campo | O que colocar |
   |---|---|
   | Razão social / Nome fantasia | Igual ao cartão CNPJ. |
   | Tipo de inscrição / CNPJ | CNPJ e o número; pode ser com ou sem pontos. |
   | Classificação tributária | Simples: **01**. Lucro Presumido/Real: **99**. MEI: **04**. |
   | Simples Nacional – Anexo IV | Só se for Simples **e** Anexo IV. Na dúvida, o contador. |
   | CNAE preponderante | Atividade principal do cartão CNPJ, 7 números. |
   | FPAS / terceiros | No Simples o sistema ignora. No Lucro, 515 / 0115 / 5,80 é o mais comum; confirmar com o contador. |
   | RAT / FAP | No Simples (fora do Anexo IV) não entram na conta. No Lucro, contador ou Domínio. |
   | CNPJ do sindicato | Da categoria dos empregados; obrigatório para admitir (S-2200). |
   | Início de validade no eSocial | Deixar **2026-01**. |
   | Município / UF / Dia do pagamento | Da empresa; dia do pagamento padrão 5. |
   | Ambiente eSocial | **Produção restrita (testes)**. |
   | CNPJ/CPF do transmissor | Em branco se o certificado for da própria empresa; CNPJ do escritório se for o certificado do escritório com procuração. |
   | Envio automático | Pode ficar marcado: sem certificado nada sai, e com certificado vai só para o ambiente de testes. |
   | Empresa já cadastrada no eSocial por outro sistema | **Desmarcado** enquanto estiver em testes (veja a seção 4). |

5. Ele pediu para **preencher com os dados da pasta de uma cliente** no PC. A sessão da nuvem não
   alcança o computador. Foi orientado a mandar print do cartão CNPJ (nunca o `.pfx` ou a senha) ou,
   melhor, a continuar numa conversa do Claude no próprio PC.
6. Perguntou se dava para "mudar o ambiente para usar no PC". Recebeu duas opções:
   - **Recomendada:** abrir o app do Claude no PC, entrar no Claude Code numa conversa nova com a
     pasta do projeto e colar a mensagem da seção 6.4;
   - liberar uma pasta para a sessão da nuvem em *Configurações → Claude Code → Remote Control*.
     Essa opção ainda não está disponível para todos e libera só uma pasta por conversa.
7. Este arquivo foi reescrito por completo, sem dados de clientes ou funcionários, porque o
   repositório é público.

Nenhum código do sistema foi alterado nesta conversa; só este arquivo.

---

## 3. Estado atual no PC do usuário

- Projeto em `C:\Users\Willyson Oliveira\Documents\cfe-updates`. Pode ser que o Windows mostre a pasta
  como `OneDrive\Documentos\cfe-updates`, se os Documentos estiverem no OneDrive; conferir.
- Provavelmente está no branch `main`. O `FolhaWeb.bat` faz `git pull --ff-only` do branch atual.
- Banco `db.sqlite3` com:
  - usuário `willysonoliveira` (superusuário dele);
  - usuário `admin`/`admin` e a empresa fictícia Padaria Pão Quente, vindos do `dados_demo`.
- Nenhuma empresa ou funcionário real cadastrado ainda. Nenhum certificado enviado.
- Os arquivos dos clientes ficam em `C:\Users\Willyson Oliveira\OneDrive\Documentos\Clientes\`.

---

## 4. Decisões tomadas

- **Django monolítico + SQLite:** simples de rodar no Windows. PostgreSQL fica opcional.
- **Assinatura XMLDSig feita à mão:** a C14N inclusiva do signxml/libxml2 2.14 quebrava com
  `xmlns=""`. Os testes verificam a assinatura de forma independente com `ET.canonicalize`.
- **Validação nos XSDs com `assinado=False`** antes de assinar, porque o XSD exige o elemento `Signature`.
- **Férias:** o INSS é retido no recibo de férias e compensado na folha, para o líquido não ficar
  negativo quando o gozo ocupa quase o mês todo.
- **S-1210 pelo regime de caixa:** o mês do pagamento, não o da competência.
- **Hospedagem:** primeiro o próprio servidor com Cloudflare Tunnel (dados ficam com o usuário); depois
  ele decidiu ficar **só local**, no PC.
- **Visual:** cor Grafite como padrão, por escolha do usuário. Os estáticos levam versão no endereço,
  porque o navegador dele ficava com o CSS antigo em cache.
- **Windows em português:** o `netstat` mostra "ESCUTANDO" em vez de "LISTENING", por isso a checagem
  de porta usa `Get-NetTCPConnection`.
- **Relatórios** usam uma estrutura genérica (`Relatorio`/`Secao`/`Coluna`) e um único template.
- O **informe de rendimentos** é só para conferência; o oficial vem do eSocial/DCTFWeb.
- **Primeiras empresas reais em "Produção restrita (testes)"** até o contador aprovar a passagem para
  Produção, porque o envio ao eSocial nunca foi testado contra o webservice real.
- **"Empresa já cadastrada no eSocial por outro sistema" desmarcada em testes.** Com ela marcada, o
  sistema não envia S-1000/S-1005/S-1020 (`esocial/servico.py`, linha 63), e o ambiente de testes do
  governo começa vazio: recusaria tudo. Ela só faz sentido em Produção, se o Domínio já cadastrou a
  empresa. O mesmo vale para "funcionário já cadastrado no eSocial" (`esocial_ja_cadastrado`).
- **A continuação deve rodar no PC dele**, porque as sessões na nuvem não alcançam o computador.
- **Nada de dados pessoais no repositório**, porque ele é público.

---

## 5. O que falta

Pendências com o usuário:
- [x] Confirmar que o sistema abre no PC. Feito em 11/11/2026.
- [ ] Cadastrar a primeira empresa real (a cliente da pasta citada na seção 0).
- [ ] Descobrir de quem é o certificado A1 e enviá-lo pela tela *Empresas → Certificado*.
- [ ] Cadastrar cargos e funcionários e calcular a primeira folha.
- [ ] Testar o eSocial em **produção restrita** (ambiente 2) com o certificado real. **Isso nunca foi
      testado contra o webservice real.**
- [ ] Decidir o que fazer com a empresa de demonstração e o usuário `admin`/`admin` (trocar a senha
      ou apagar).
- [ ] Combinar uma rotina de backup do `db.sqlite3` (pendrive ou Google Drive).
- [ ] Avaliar deixar o repositório **privado** no GitHub. Nesse caso o `git pull` do `FolhaWeb.bat`
      vai pedir login do GitHub no PC na primeira vez.

Pontos para o contador confirmar (também no README):
- naturezas de férias 1015/1016/1017/9221;
- abono pecuniário com natureza 1023 e IRRF 74;
- rescisão: naturezas 6006/6007/6129/9299 e IRRF 73;
- retenção antecipada do INSS das férias (rubrica 9209, natureza 9200);
- redutor da Lei 15.270 no 13º e nas férias;
- nome do serviço do Integra Contador (`GERARGUIA31`);
- FPAS, terceiros, RAT e FAP de cada empresa real.

Melhoria sugerida (ainda não feita):
- Fazer `esocial_ja_iniciado` (empresa) e `esocial_ja_cadastrado` (funcionário) só valerem quando
  `ambiente_esocial == 1` (Produção). Hoje elas pulam os eventos de cadastro em qualquer ambiente
  (`esocial/servico.py`, linhas 63, 67, 97, 120 e 370), o que faz o ambiente de testes recusar tudo.

Funcionalidades ainda não feitas (ideias):
- Retificação de folha enviada (S-1200 com `indRetif=2`) e exclusão de eventos (S-3000).
- Afastamentos por doença/maternidade, alterações contratuais (S-2205/S-2206) e SST (S-2210/S-2220/S-2240).
- Férias coletivas, férias em dobro, pensão alimentícia, consignado, horistas e intermitentes.
- Feriados nacionais e municipais nos prazos.
- Leitura dos totalizadores S-5001/S-5011.
- Restaurar backup pela tela. Hoje só existe o zip; o usuário perguntou como levar dados do servidor para o PC.
- Acessar de outros computadores da rede local, se ele pedir.
- Ler o cartão CNPJ (PDF) e preencher a empresa sozinho, se fizer sentido.

---

## 6. Como rodar

### 6.1 No PC (uso atual, só local)
1. Dois cliques em **`FolhaWeb.bat`** ou no atalho **FolhaWeb** da Área de Trabalho. Pelo PowerShell:
   `cd "$HOME\Documents\cfe-updates"` e depois `.\FolhaWeb.bat`. Ele faz sozinho:
   - `git pull --ff-only`;
   - cria a `.venv` e roda `pip install -r requirements.txt`;
   - `migrate`;
   - `createsuperuser` se ainda não houver usuário;
   - cria o atalho e abre o navegador.

   Ele força `FOLHA_DEBUG=true` e usa o `runserver` em `127.0.0.1:8000`.
2. Abrir `http://127.0.0.1:8000` e entrar com `willysonoliveira`.
3. A janela preta precisa ficar aberta enquanto o sistema é usado.
4. Esqueceu a senha: `.venv\Scripts\python.exe manage.py changepassword willysonoliveira`.
5. Outro usuário: `.venv\Scripts\python.exe manage.py createsuperuser`.
6. Dados de teste: `.venv\Scripts\python.exe manage.py dados_demo` cria a Padaria Pão Quente com
   funcionários fictícios, folhas de jan a out/2026 e o usuário `admin`/`admin`. Já foi rodado no PC dele.
7. Backup: copiar o `db.sqlite3`, ou rodar `manage.py backup`, que gera um zip em `backups/` com o
   banco, os certificados e o `.env`.

### 6.2 Linux / desenvolvimento
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python manage.py migrate && python manage.py dados_demo && python manage.py runserver
python manage.py test        # 76 testes, todos passando em 11/11/2026
```

### 6.3 Publicar na internet (pronto, mas NÃO está em uso)
- **`Servidor.bat`:**
  - cria o `.env` de produção (`preparar_servidor`), roda `collectstatic`, faz backup;
  - liga a fila do eSocial a cada 5 minutos (`processar_esocial --intervalo 300`);
  - sobe o Waitress (`manage.py servir`) em 127.0.0.1:8000;
  - abre o Cloudflare Tunnel, nesta ordem de prioridade: token em `FOLHA_CLOUDFLARE_TOKEN`, depois
    `tools/cloudflared.yml`, depois o endereço provisório `trycloudflare.com` (salvo em `ENDERECO.txt`).
- **`InstalarNoServidor.bat`** usa `scripts/tarefas-windows.ps1` para criar tarefas do Windows (SYSTEM):
  ligar com o Windows, religar se cair e backup diário às 2h. Para desfazer: `/remover`.
- **`ConfigurarDominio.bat`** (domínio próprio):
  - faz `cloudflared tunnel login`, cria o túnel `folhaweb-<PC>` e roda `route dns`;
  - chama `manage.py configurar_dominio`, que grava o yml, ajusta o `.env` e salva `ENDERECO.txt`;
  - exige o domínio já **Active** na Cloudflare, com os nameservers trocados no Registro.br;
  - antes, conferir se os registros MX/TXT do e-mail foram copiados.
- Os `.bat` são só ASCII e CRLF (`.gitattributes`). Só o `FolhaWeb.bat` foi usado de fato num Windows
  real, e funcionou.

### 6.4 Continuar numa conversa nova no PC
No app do Claude no computador, abrir o Claude Code numa conversa nova com a pasta do projeto e colar:

```text
O projeto FolhaWeb já está em C:\Users\Willyson Oliveira\Documents\cfe-updates (se não estiver, procure em OneDrive\Documentos\cfe-updates). Use essa pasta, não baixe outra cópia e não apague o db.sqlite3. Busque e troque para o branch claude/gracious-bell-4jgktd do repositório willynelsonn/cfe-updates, leia o HISTORICO.md e continue de onde parou: cadastrar no FolhaWeb a empresa da cliente cuja pasta está em C:\Users\Willyson Oliveira\OneDrive\Documentos\Clientes\CLIENTES DIVERSOS\<nome da cliente>.
```

Trocar `<nome da cliente>` pelo nome da pasta. Trocar de branch não mexe no `db.sqlite3`, no `.env` nem
nos certificados, porque eles ficam fora do Git.

---

## 7. PRs e branches (`willynelsonn/cfe-updates`)

| PR | Conteúdo |
|---|---|
| #1 | Criação do FolhaWeb (folha + eSocial); 13º, férias, envio automático, guias e conformidade; rescisão, custos, painel e primeiro redesenho |
| #2 | Navegação em pílula, GSAP, cena Three.js no login, seis cores e seletor de aparência |
| #3 | Grafite como cor padrão e estáticos com versão (problema de cache) |
| #4 | `FolhaWeb.bat` (atualiza e inicia com dois cliques) |
| #5 | Publicação no servidor: `Servidor.bat`, instalador, segurança, backup, Waitress |
| #6 | Central de 20 relatórios e `ConfigurarDominio.bat` |

Todos foram mergeados na `main` a partir do branch `claude/nifty-einstein-6lgypb`.

Branches:
- `main`: código do sistema, sem este arquivo.
- `claude/nifty-einstein-6lgypb`: conversa 1; tem a primeira versão deste arquivo.
- `claude/gracious-bell-4jgktd`: conversa 2; tem esta versão. Não há PR aberto para ele.
