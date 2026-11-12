# Histórico do projeto FolhaWeb (Sistema de folha de pagamento)

Este arquivo resume a conversa em que o sistema foi construído (sessão na nuvem "Sistema de folha de
pagamento"), para que uma conversa nova continue o trabalho sem perder contexto.
Leia também o `README.md`, que é o manual de uso e instalação.

- **Repositório:** `willynelsonn/cfe-updates` (GitHub)
- **Branch de trabalho:** `claude/nifty-einstein-6lgypb`. A `main` tem o mesmo código; os PRs #1 a #6 já foram mergeados.
- **Dono / usuário:** Willyson Oliveira. O sistema é para o primo dele (departamento pessoal / escritório).
  Ele fala português e não é programador: as instruções devem ser simples, passo a passo, com
  comandos prontos para colar no PowerShell e pedindo print quando algo der errado.

---

## 1. O que foi pedido (em ordem)

1. Um site/app para **registrar funcionários, enviar ao eSocial, DCTFWeb, FGTS e controlar a folha
   completa**. O usuário tem o Domínio Sistemas instalado no servidor dele (não foi inspecionado).
2. **13º salário e férias**, com **tudo automatizado**:
   - o cadastro vai sozinho ao eSocial;
   - um botão de apuração calcula e envia;
   - um botão gera as guias.

   Pedido de postura: "aja como analista sênior do Ministério do Trabalho" (sempre conforme a lei) e
   "engenheiro sênior" (site intuitivo, com todo botão dizendo para que serve).
3. **Rescisão**, **custo de cada funcionário para a empresa** e um **painel/dashboard** de alto nível.
   Achou o primeiro layout "amador" e pediu redesenho.
4. Redesenho com referências de animação (Three.js, GSAP, motion design), depois **mais opções de
   cor**. Escolheu a cor **Grafite** (preto e branco), que virou a padrão.
5. Automatizar os passos do PowerShell: daí veio o **`FolhaWeb.bat`** (dois cliques).
6. "Publica na internet". Escolheu **hospedar no próprio servidor** com Cloudflare Tunnel: daí vieram
   o `Servidor.bat`, o `InstalarNoServidor.bat` e, depois, o `ConfigurarDominio.bat`.
7. **"Todos os relatórios possíveis para a folha"**: central com 20 relatórios.
8. Pediu para rodar só no PC (*"dentro do meu PC, não na internet"*) e depois mudou para
   **"concluir o processo de postar o site no cloud + Supabase"**. Foi feito o suporte a **Render
   (hospedagem) + Supabase (PostgreSQL)**, com o `render.yaml`. O Cloudflare não roda Django, então
   foi usado o Render. A criação das contas e o deploy dependem do usuário (seção 4).

O usuário sempre pediu **"crie o PR e faça o merge"** ao fim de cada etapa.

---

## 2. Estado atual no PC do usuário

- Projeto clonado em `C:\Users\Willyson Oliveira\Documents\cfe-updates`.
- O Python e o Git já estavam instalados. O instalador do Git tentou atualizar e travou com processos
  "bash" abertos; a orientação foi cancelar, porque o Git já funcionava.
- Rodou o `FolhaWeb.bat` com sucesso: o servidor de desenvolvimento subiu em `http://127.0.0.1:8000`.
- Criou o superusuário **`willysonoliveira`** com `manage.py createsuperuser`. Recebeu o aviso de senha
  fraca e a orientação de usar 8+ caracteres com letras e números; o resultado foi "Superuser created
  successfully".
- Depois disse que "não abriu o site". Causa provável: a janela do `FolhaWeb.bat` tinha sido fechada.
  A orientação foi rodar `.\FolhaWeb.bat` no PowerShell e acessar `http://127.0.0.1:8000`. **Não houve
  confirmação de que funcionou**: vale conferir isso primeiro na conversa nova.
- Ainda **não cadastrou** a empresa real nem funcionários reais.
- A sessão da nuvem **não tinha acesso ao PC dele**: `list_computer_folders` voltava vazio. Por isso
  tudo foi feito por instruções.

---

## 3. O que o sistema faz

Django 5.2, Python 3.12+ (desenvolvido no 3.13), SQLite por padrão (PostgreSQL opcional via `FOLHA_DB_ENGINE=postgres`).

Apps:
- **`empresas`**:
  - várias empresas, CNPJ, Simples/Lucro, RAT/FAP, terceiros;
  - certificado A1 com senha cifrada pela `FOLHA_SECRET_KEY`;
  - middleware de empresa ativa;
  - comandos `dados_demo`, `backup`, `preparar_servidor`, `servir` e `configurar_dominio`.
- **`pessoal`**: funcionários (dados completos para o S-2200), dependentes (IRRF e salário-família), cargos com CBO.
- **`folha`**:
  - rubricas (S-1010) e competências;
  - cálculo da folha (`servico.py`, `calculo.py`, `tabelas.py`);
  - férias, 13º, rescisão (`rescisao.py`), custos (`custo.py`), painel (`painel.py`);
  - conformidade legal (`conformidade.py`), guias (`guias.py`), **relatórios (`relatorios.py`)**.
- **`esocial`**:
  - geração dos XML (`xml_eventos.py`) e validação nos XSDs oficiais (`schemas/`);
  - assinatura XMLDSig (`assinatura.py`), SOAP de lote e consulta (`webservice.py`);
  - fila com dependências entre eventos (`servico.py`);
  - Integra Contador / SERPRO para o DARF (`integra_contador.py`).

Funcionalidades (detalhe na tabela do README):
- **eSocial S-1.3:**
  - eventos S-1000, S-1005, S-1010, S-1020, S-2200, S-2230, S-2299, S-1200, S-1210 e S-1299;
  - assinados e transmitidos em lote, com fila automática;
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
  - Controle: provisão de férias e 13º, controle de férias vencidas/a vencer, contratos a vencer (e o link para Custos);
  - Pessoas: relação de funcionários, admissões e desligamentos, aniversariantes, dependentes;
  - para criar um relatório novo: escreva `fn(empresa, filtros) -> Relatorio` e registre em `RELATORIOS`.
- **Interface:**
  - navegação em pílulas; fontes Plus Jakarta Sans e Instrument Serif;
  - GSAP 3.13 + ScrollTrigger e Three.js r170 (só no login), em `static/vendor`;
  - 6 temas de cor (`data-cor`) com a ordem dos gráficos validada para daltonismo; o padrão é Grafite (`FOLHA_COR_PADRAO`);
  - modo claro/escuro;
  - a tag `{% estatico %}` acrescenta `?v=mtime` para não ficar em cache.
- **Segurança (modo servidor, `FOLHA_DEBUG=false`):**
  - `.env` carregado pelo `settings`;
  - WhiteNoise, cookies seguros, sessão de 8h, cabeçalhos de segurança;
  - bloqueio de login após 5 erros por 15 minutos, por usuário e por IP via `CF-Connecting-IP` (`config/seguranca.py`);
  - o login do admin passa pela mesma tela;
  - log em `folhaweb.log`.

---

## 4. Como rodar

### No PC (uso atual, só local)
1. Dois cliques em **`FolhaWeb.bat`** ou no atalho **FolhaWeb** da Área de Trabalho. Ele faz sozinho:
   - `git pull --ff-only`;
   - cria a `.venv` e roda `pip install -r requirements.txt`;
   - `migrate`;
   - `createsuperuser` se ainda não houver usuário;
   - cria o atalho e abre o navegador.

   Ele força `FOLHA_DEBUG=true` e usa o `runserver` em `127.0.0.1:8000`.
2. Entrar com o usuário `willysonoliveira`.
3. A janela preta precisa ficar aberta enquanto o sistema é usado.
4. Para criar outro usuário: `cd $HOME\Documents\cfe-updates` e `.venv\Scripts\python.exe manage.py createsuperuser`.
5. Dados de teste (opcional): `.venv\Scripts\python.exe manage.py dados_demo` cria a "Padaria Pão
   Quente", 8 funcionários, folhas e o usuário `admin`/`admin`.
6. Backup: copiar o `db.sqlite3`, ou rodar `manage.py backup`, que gera um zip em `backups/` com o
   banco, os certificados e o `.env`.

### Linux / desenvolvimento
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python manage.py migrate && python manage.py dados_demo && python manage.py runserver
python manage.py test        # 78 testes, todos passando no último commit
```

### Nuvem: Render + Supabase (pedido mais recente; contas ainda não criadas)
- O passo a passo está no README, em "Publicar na nuvem (Render + Supabase)".
- `render.yaml` (Blueprint):
  - roda `pip install` e `collectstatic`;
  - na partida: `migrate`, `createsuperuser --noinput` (pelas variáveis `DJANGO_SUPERUSER_*`) e
    `servir --host 0.0.0.0 --nuvem` (Waitress confiando no proxy do Render);
  - região virginia, plano free.
- `FOLHA_DATABASE_URL`: URI do Supabase (Session pooler, porta 5432). Também funciona o pooler 6543,
  que desliga as conexões persistentes. SSL é obrigatório (`sslmode=require`).
- Certificados A1 ficam no banco (`ArquivoPrivado` + `empresas/armazenamento.py`), ligados
  automaticamente quando há `FOLHA_DATABASE_URL`.
- Depois de cada `migrate` em PostgreSQL (`empresas/apps.py`), o sistema liga o RLS em todas as
  tabelas e faz REVOKE para `anon`/`authenticated`. Assim a Data API do Supabase não expõe os dados.
- Testado com PostgreSQL 16 local: suíte completa e login HTTPS atrás de proxy simulado.
  **Não foi testado no Render nem no Supabase de verdade.**
- Se o PC e a nuvem usarem o mesmo banco, use a mesma `FOLHA_SECRET_KEY`; senão a senha do
  certificado não é lida.

### Publicar a partir do próprio servidor (Cloudflare Tunnel; alternativa, não está em uso)
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
  - antes, é preciso conferir se os registros MX/TXT do e-mail foram copiados. O usuário estava
    mexendo em TXT/MX no Registro.br.
- Os `.bat` são só ASCII e CRLF (`.gitattributes`). **Nenhum `.bat` foi testado num Windows real**:
  só o `FolhaWeb.bat` foi usado de fato pelo usuário, e funcionou.

---

## 5. Decisões tomadas

- **Django monolítico + SQLite:** simples de rodar no Windows do usuário. PostgreSQL fica opcional.
- **Assinatura XMLDSig feita à mão:** a C14N inclusiva do signxml/libxml2 2.14 quebrava com
  `xmlns=""`. Os testes verificam a assinatura de forma independente com `ET.canonicalize`.
- **Validação nos XSDs com `assinado=False`** antes de assinar, porque o XSD exige o elemento `Signature`.
- **Férias:** o INSS é retido no recibo de férias e compensado na folha, para o líquido não ficar
  negativo quando o gozo ocupa quase o mês todo.
- **S-1210 pelo regime de caixa:** o mês do pagamento, não o da competência.
- **Hospedagem:** o próprio servidor/PC com Cloudflare Tunnel, em vez de nuvem paga, para os dados
  ficarem com o usuário. Depois o usuário decidiu ficar **só local**.
- **Visual:** cor Grafite como padrão, por escolha do usuário. Os estáticos levam versão no endereço,
  porque o navegador dele ficava com o CSS antigo em cache.
- **No Windows em português**, `netstat` mostra "ESCUTANDO" em vez de "LISTENING". Por isso a checagem
  de porta usa `Get-NetTCPConnection`.
- Os relatórios usam uma estrutura genérica (`Relatorio`/`Secao`/`Coluna`) e um único template, em vez
  de um template por relatório.
- O **informe de rendimentos** é só para conferência; o oficial vem do eSocial/DCTFWeb. Precisa de
  confirmação do contador.

---

## 6. O que falta / próximos passos

Pendências com o usuário:
- [ ] Criar as contas no Supabase e no Render e fazer o deploy (README). Conferir o login no endereço `onrender.com`.
- [ ] Confirmar que o sistema abre no PC dele (`FolhaWeb.bat` aberto e `http://127.0.0.1:8000`).
- [ ] Cadastrar a empresa real: CNPJ, regime, RAT/FAP, certificado A1 `.pfx` e senha.
- [ ] Cadastrar cargos e funcionários e calcular a primeira folha.
- [ ] Testar o eSocial em **produção restrita** (ambiente 2) com o certificado real. **Isso nunca foi
      testado contra o webservice real.**
- [ ] Combinar uma rotina de backup do `db.sqlite3` (pendrive ou Google Drive).

Pontos para o contador confirmar (também no README):
- naturezas de férias 1015/1016/1017/9221;
- abono pecuniário com natureza 1023 e IRRF 74;
- rescisão: naturezas 6006/6007/6129/9299 e IRRF 73;
- retenção antecipada do INSS das férias (rubrica 9209, natureza 9200);
- redutor da Lei 15.270 no 13º e nas férias;
- nome do serviço do Integra Contador (`GERARGUIA31`).

Funcionalidades ainda não feitas (ideias):
- Retificação de folha enviada (S-1200 com `indRetif=2`) e exclusão de eventos (S-3000).
- Afastamentos por doença/maternidade, alterações contratuais (S-2205/S-2206) e SST (S-2210/S-2220/S-2240).
- Férias coletivas, pensão alimentícia, consignado, horistas e intermitentes.
- Feriados nacionais e municipais nos prazos.
- Leitura dos totalizadores S-5001/S-5011.
- Restaurar backup pela tela. Hoje só existe o zip; o usuário perguntou como levar dados do servidor para o PC.
- Acessar de outros computadores da rede local, se ele pedir.

---

## 7. PRs já mergeados (`willynelsonn/cfe-updates`)

| PR | Conteúdo |
|---|---|
| #1 | Criação do FolhaWeb (folha + eSocial); 13º, férias, envio automático, guias e conformidade; rescisão, custos, painel e primeiro redesenho |
| #2 | Navegação em pílula, GSAP, cena Three.js no login, seis cores e seletor de aparência |
| #3 | Grafite como cor padrão e estáticos com versão (problema de cache) |
| #4 | `FolhaWeb.bat` (atualiza e inicia com dois cliques) |
| #5 | Publicação no servidor: `Servidor.bat`, instalador, segurança, backup, Waitress |
| #6 | Central de 20 relatórios e `ConfigurarDominio.bat` |
| #7 | Este `HISTORICO.md` |
| #8 | Nuvem: Render + Supabase (`render.yaml`, banco por URL, certificados no banco, RLS) |
