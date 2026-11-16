# Portal do cliente, fase 1 (base) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A dona de uma empresa cria conta e cadastra a empresa (ou entra por convite), o escritório confere e libera, e
quem não é do escritório fica preso ao portal `/cliente/`, vendo só a própria empresa.

**Architecture:** App novo `portal` (telas públicas e da cliente) + modelos `Acesso` e `Convite` e o campo
`Empresa.situacao` no app `empresas`. Um middleware bloqueia por padrão tudo que não é portal para quem não é
`is_staff`, e o `EmpresaAtivaMiddleware` passa a escolher a empresa da cliente só entre os vínculos dela.

**Tech Stack:** Django 5.2, Postgres (Supabase) / SQLite nos testes, `requests` (já instalado) para a BrasilAPI.

**Spec:** `docs/superpowers/specs/2026-11-16-portal-do-cliente-design.md` (seções 1, 2, 3 e Segurança)

## Global Constraints

- Escritório = `user.is_staff`. Cliente = autenticado, sem `is_staff`.
- Cliente só acessa: `/cliente/`, `/sair/`, `/conta/` (senha e preferências), `/static/`, `/cadastro/`, `/convite/`,
  `/termos/`, `/privacidade/`. Resto: GET → redirect `/cliente/`; outros métodos → 403.
- Objeto de outra empresa = 404.
- Empresa cadastrada pela dona: `situacao="em_analise"`, `ativa=False`. Empresas existentes e as criadas pelo
  escritório: `situacao="ativa"`.
- Liberar: `situacao="ativa"`, `ativa=True`, `envio_automatico=False`, transmissor = `settings.FOLHA_ESCRITORIO_CNPJ`
  se vazio, `criar_rubricas_padrao(empresa)`.
- Convite: uso único, vale 7 dias; o banco guarda só o SHA-256 do código.
- Cadastro: no máximo `settings.CADASTRO_MAX_POR_HORA` (padrão 5) por IP por hora; campo-armadilha `site` deve vir vazio.
- Termos: `TERMOS_VERSAO = "2026-11-16"`; aceite guarda versão e data/hora no `Acesso`.
- Usuário da dona = e-mail em minúsculas. Login aceita o e-mail com qualquer caixa.
- Textos da cliente em português simples; testes só com dados inventados (repositório público).

## Review Focus

1. Cliente com `empresa_id` de outra empresa na sessão → continua vendo só a própria (Task 2).
2. CNPJ digitado com ou sem pontuação já existente → mensagem neutra, nada criado (Task 4).
3. Dona digita o e-mail com maiúsculas no login → entra (Task 4).
4. BrasilAPI fora do ar ou lenta → cadastro continua, pedindo o nome da empresa (Task 4).
5. Pessoa do escritório abre `/cliente/` → vai para o painel do escritório, sem erro (Task 3).

---

### Task 1: Dados (situação, acesso, convite)

**Files:**
- Modify: `empresas/models.py` (Empresa + 2 modelos novos)
- Create: migração `empresas/migrations/0005_portal_base.py` (makemigrations)
- Test: `portal/tests/test_modelos.py` (cria o app `portal` vazio: `portal/__init__.py`, `apps.py`, `tests/__init__.py`;
  `"portal"` em `INSTALLED_APPS`)

**Interfaces:**
- Produces:
  - `Empresa.SITUACAO = [("em_analise","Em análise"),("ativa","Ativa"),("recusada","Recusada")]`;
    `situacao` (default `"ativa"`), `motivo_recusa` (texto, blank), `validada_em` (datetime null), `validada_por` (FK User null).
  - `Acesso(usuario FK User related_name="acessos", empresa FK Empresa related_name="acessos", termos_versao str,
    termos_aceitos_em datetime, criado_em)`; `unique_together = (usuario, empresa)`.
  - `Convite(empresa FK, codigo_hash str(64) unique, criado_por FK User null, criado_em, usado_em null, usado_por FK User null)`;
    `Convite.criar(empresa, por) -> tuple[Convite, str]` (devolve o código em claro, uma vez);
    `Convite.pelo_codigo(codigo) -> Convite | None` (só válido: não usado e com menos de 7 dias).

- [ ] **Step 1:** Teste `test_convite_vale_uma_vez_e_expira_em_7_dias`: `criar` → `pelo_codigo(codigo)` acha;
  marcar `usado_em` → `None`; outro convite com `criado_em` 8 dias atrás → `None`; código errado → `None`.
  Teste `test_empresa_nova_nasce_ativa`: `Empresa.objects.create(...)` → `situacao == "ativa"`.
- [ ] **Step 2:** `python manage.py test portal` → falha (modelos não existem).
- [ ] **Step 3:** Implementar modelos; código com `secrets.token_urlsafe(32)`, hash `hashlib.sha256`; `makemigrations empresas -n portal_base`.
- [ ] **Step 4:** Testes passam.
- [ ] **Step 5:** Commit.

### Task 2: Bloqueio por padrão e empresa da cliente

**Files:**
- Create: `empresas/acesso.py`
- Modify: `empresas/middleware.py`, `empresas/context_processors.py` (`empresas_disponiveis` da cliente = só as dela),
  `config/settings.py` (MIDDLEWARE: `empresas.middleware.PortalMiddleware` logo depois de `EmpresaAtivaMiddleware`)
- Test: `portal/tests/test_acesso.py`

**Interfaces:**
- Produces: `eh_escritorio(user) -> bool`; `empresas_do_usuario(user) -> QuerySet[Empresa]` (via `Acesso`, qualquer
  situação); `ROTAS_DA_CLIENTE: tuple[str, ...]` (prefixos da lista em Global Constraints).

- [ ] **Step 1:** Testes (duas empresas A e B, dona_a com Acesso a A, staff):
  `test_cliente_get_em_rota_do_escritorio_vai_para_portal` (`/folha/`, `/empresas/`, `/admin/` → 302 `/cliente/`);
  `test_cliente_post_em_rota_do_escritorio_e_403` (`/empresas/nova/`);
  `test_sessao_com_outra_empresa_nao_vaza` (sessão `empresa_id=B.pk` → `request.empresa == A`, via resposta de `/cliente/`
  mostrando o nome de A e não o de B);
  `test_cliente_sem_vinculo_fica_sem_empresa` (`request.empresa is None`, nunca "a primeira ativa");
  `test_escritorio_continua_igual` (`/folha/` 200 para staff); `test_anonimo_continua_indo_para_login`.
- [ ] **Step 2:** Rodar → falham.
- [ ] **Step 3:** `PortalMiddleware.__call__`: autenticado, não staff, caminho fora de `ROTAS_DA_CLIENTE` → regra de
  Global Constraints. `EmpresaAtivaMiddleware`: se não staff, empresa = sessão ∩ `empresas_do_usuario`, senão a primeira
  delas, senão `None`.
- [ ] **Step 4:** Testes passam; suíte inteira passa.
- [ ] **Step 5:** Commit.

### Task 3: Portal mínimo `/cliente/` (situação do cadastro)

**Files:**
- Create: `portal/urls.py`, `portal/views.py` (`inicio`), `templates/portal/base.html` (layout de celular, `app.css`
  + tokens do FolhaWeb, sem a barra do escritório), `templates/portal/inicio.html`
- Modify: `config/urls.py` (`path("", include("portal.urls"))`)
- Test: `portal/tests/test_inicio.py`

**Interfaces:**
- Produces: URL names `portal:inicio` (`/cliente/`), e o template base `portal/base.html` (blocks `title`, `conteudo`).

- [ ] **Step 1:** Testes: em análise → contém "Recebemos seu cadastro" e o passo a passo da procuração (CNPJ do
  escritório de `settings.FOLHA_ESCRITORIO_CNPJ` formatado); recusada → contém o `motivo_recusa`; ativa → contém
  "Tudo certo" e o nome da empresa; staff em `/cliente/` → 302 para `/`; anônimo → login.
- [ ] **Step 2:** Rodar → falham.
- [ ] **Step 3:** View `inicio` (login_required). Settings novos: `FOLHA_ESCRITORIO_CNPJ` e `FOLHA_ESCRITORIO_NOME`
  (env, padrão vazio / "seu escritório").
- [ ] **Step 4:** Testes passam.
- [ ] **Step 5:** Commit.

### Task 4: Cadastro aberto, termos e login por e-mail

**Files:**
- Create: `empresas/consulta_cnpj.py`, `portal/forms.py` (`CadastroForm`), `templates/portal/cadastro.html`,
  `templates/portal/termos.html`, `templates/portal/privacidade.html` (rascunhos, marcados para revisão do escritório)
- Modify: `portal/views.py` (`cadastro`, `termos`, `privacidade`), `portal/urls.py`, `config/seguranca.py`
  (e-mail em minúsculas no login), `templates/login.html` (texto + link "Cadastrar minha empresa")
- Test: `portal/tests/test_cadastro.py`

**Interfaces:**
- Produces: `consultar_cnpj(cnpj: str) -> dict | None` com chaves `razao_social, nome_fantasia, cnae, municipio, uf`
  (GET `https://brasilapi.com.br/api/cnpj/v1/{cnpj}`, timeout 5 s, qualquer erro → `None`);
  `TERMOS_VERSAO` em `portal/forms.py`; URL names `portal:cadastro`, `portal:termos`, `portal:privacidade`.
- `CadastroForm` campos: `nome, cpf, email, celular, cnpj, razao_social (opcional), funcionarios (int ≥0),
  senha1, senha2, aceite (obrigatório), site (armadilha)`.

- [ ] **Step 1:** Testes (`consultar_cnpj` com `patch`):
  `test_cadastro_cria_dona_empresa_em_analise_e_acesso` (usuário = e-mail minúsculo, empresa `em_analise`/`ativa=False`
  com dados da BrasilAPI, Acesso com `termos_versao`, já logada, redirect `/cliente/`);
  `test_cnpj_ja_existe_com_ou_sem_pontuacao_da_mensagem_neutra` (nada criado; texto "Essa empresa já tem cadastro");
  `test_email_ja_usado`; `test_cpf_e_cnpj_invalidos`; `test_sem_aceite_nao_cadastra`;
  `test_armadilha_preenchida_nao_cria_nada`; `test_limite_por_ip` (6ª tentativa no mesmo IP → bloqueada);
  `test_brasilapi_fora_pede_nome_da_empresa` (consulta `None` e `razao_social` vazio → erro no campo; preenchido → cria);
  `test_login_com_email_em_maiusculas`; `test_termos_e_privacidade_abrem_sem_login`.
- [ ] **Step 2:** Rodar → falham.
- [ ] **Step 3:** Implementar. Senha validada com `password_validation.validate_password`. Tudo em `transaction.atomic`.
  Limite por IP com `cache` e `ip_do_cliente` de `config/seguranca.py`.
- [ ] **Step 4:** Testes passam.
- [ ] **Step 5:** Commit.

### Task 5: Validação da empresa pelo escritório

**Files:**
- Modify: `empresas/views.py` (`validar`), `empresas/urls.py` (`<int:pk>/validar/`, name `validar`),
  `templates/empresas/lista.html` (tag da situação; botão "Conferir" para em análise),
  `empresas/context_processors.py` (`empresas_para_conferir` para staff), `templates/dashboard.html` (aviso com o número)
- Create: `templates/empresas/validar.html`
- Test: `portal/tests/test_validacao.py`

- [ ] **Step 1:** Testes: `test_liberar_ativa_e_cria_rubricas` (POST `acao=liberar` com o EmpresaForm válido →
  regras de Global Constraints; `Rubrica` da empresa existe; `validada_por` = staff);
  `test_recusar_exige_motivo` (sem motivo: continua em análise; com motivo: `recusada`, `ativa=False`);
  `test_cliente_nao_valida` (dona → 403); `test_lista_mostra_conferir`.
- [ ] **Step 2:** Rodar → falham.
- [ ] **Step 3:** View só para `is_staff` (`user_passes_test`), usando `EmpresaForm` para os campos técnicos.
- [ ] **Step 4:** Testes passam.
- [ ] **Step 5:** Commit.

### Task 6: Convite para a dona

**Files:**
- Modify: `empresas/views.py` (`convidar`: POST staff → cria `Convite`, mostra o link e um botão
  `https://wa.me/?text=<link>`), `empresas/urls.py` (`<int:pk>/convidar/`), `templates/empresas/lista.html`,
  `portal/views.py` (`convite`), `portal/forms.py` (`ConviteForm`: nome, cpf, email, senha1, senha2, aceite),
  `portal/urls.py` (`convite/<str:codigo>/`, name `convite`)
- Create: `templates/empresas/convite_link.html`, `templates/portal/convite.html`
- Test: `portal/tests/test_convite.py`

- [ ] **Step 1:** Testes: `test_convite_cria_conta_e_vinculo_uma_vez` (segunda abertura → 404);
  `test_convite_vencido_404`; `test_dona_logada_aceita_convite_de_outra_empresa` (só botão "Vincular", ganha 2º Acesso);
  `test_so_escritorio_gera_convite`; `test_link_mostrado_uma_vez_e_banco_guarda_so_hash`.
- [ ] **Step 2:** Rodar → falham.
- [ ] **Step 3:** Implementar com `Convite.criar` / `Convite.pelo_codigo` (Task 1).
- [ ] **Step 4:** Suíte inteira passa.
- [ ] **Step 5:** Commit, push, PR e merge (regra do dono: fim de etapa = PR + merge); conferir a publicação no Render.
