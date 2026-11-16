# Portal do cliente, fase 2: Pedidos da dona — plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A dona faz pedidos pelo portal (contratei, vai sair, férias, alterar dados, documento, dúvida), conversa e manda anexos; o escritório confere, devolve ou aprova abrindo o formulário técnico que já existe, e só aí algo toca as tabelas de funcionário, férias ou rescisão.

**Architecture:** Modelos `Pedido`, `Mensagem` e `Anexo` no app `portal`. As respostas ficam em JSON dentro do pedido. Telas da dona em `/cliente/pedidos/…` (liberadas pelo `PortalMiddleware`); telas do escritório em `/pedidos/…` (bloqueadas para a dona por padrão e com `user_passes_test(eh_escritorio)`). Aprovar = abrir `pessoal:novo`, `pessoal:editar`, `folha:ferias_nova` ou `folha:rescisao_nova` com `?pedido=<id>`; ao salvar com sucesso, o pedido guarda o vínculo e vira "Aprovado". "Concluído" vem do evento do eSocial aceito.

**Tech Stack:** Django 5.2, testes `manage.py test` (SQLite), armazenamento privado já existente (`empresas.models._storage_privado` → `BancoStorage` na nuvem).

**Spec:** `docs/superpowers/specs/2026-11-16-portal-do-cliente-design.md` (seção 4 "Pedidos", "Segurança", "Dados novos").

## Global Constraints

- Repositório público: testes só com dados inventados; nenhuma senha, certificado ou dado real.
- "Nada do pedido toca as tabelas de funcionário, férias ou rescisão antes da aprovação."
- Objeto de outra empresa = 404 (não 403).
- Linguagem simples nas telas da dona; palavra técnica só com explicação.
- Anexos no armazenamento privado já usado para certificados; visíveis só ao escritório e à dona daquela empresa.
- Migrações só adicionam.
- Comandos: `.venv/Scripts/python.exe manage.py test` a partir da pasta do projeto (o `.venv` fica em `../cfe-updates/.venv`).

## Decisões deste plano (rulings)

- Escopo pedido pela sessão principal: "fase 2" = Pedidos (o desenho numera Pedidos como fase 3). S-2205/S-2206 ficam fora: "Alterar dados" aprovado vira "Concluído" na hora, porque nada vai ao eSocial.
- Custo estimado no "Contratei alguém" fica para depois (o simulador já existe no escritório).
- Abrir o pedido no escritório muda "Enviado" para "Em análise" (o escritório é uma pessoa só).
- "Concluído" é atualizado quando alguém abre a lista ou o pedido (consulta ao `Evento` aceito), sem mexer no envio do eSocial.
- Empresa em análise ou recusada: só "Mandar documento" e "Dúvida".
- Mensagem da dona num pedido devolvido = reenviar (volta a "Enviado").
- Anexo: até 5 MB; PDF, JPG ou PNG conferidos pelos primeiros bytes (não pela extensão); baixado como anexo.

## Review Focus

1. Dona trocando IDs na URL (pedido, anexo) de outra empresa → 404 em todas as rotas `/cliente/pedidos/…`.
2. Dona escolhendo no formulário uma pessoa de outra empresa (POST com `funcionario=<id de B>`) → erro de formulário, nada gravado.
3. Escritório com outra empresa ativa na sessão clicando "Aprovar" → a sessão passa para a empresa do pedido; formulário técnico salvo com `?pedido` de outra empresa não aprova nada.
4. Arquivo `.pdf` que é um executável, ou maior que 5 MB → recusado com mensagem clara; nada gravado.
5. Pedido aprovado, cancelado ou concluído não volta: cancelar/devolver/aprovar fora de "aberto" → 404.

---

### Task 1: Modelos, anexos e migração

**Files:**
- Create: `portal/models.py`, `portal/anexos.py`, `portal/migrations/0001_pedidos.py`, `portal/tests/test_pedido_modelos.py`
- Modify: `portal/tests/fabrica.py` (helper `usar_banco_nos_anexos()`)

**Interfaces:**
- Produces:
  - `Pedido` (empresa, criado_por, tipo, situacao, respostas: JSON, funcionario/ferias/rescisao FKs opcionais `SET_NULL`, criado_em, atualizado_em). `TIPOS` = contratei, sair, ferias, alterar, documento, duvida. `SITUACOES` = enviado, em_analise, devolvido, aprovado, concluido, cancelado. `ABERTOS = ("enviado", "em_analise", "devolvido")`.
  - `Pedido.mudar(situacao: str, por: User | None, texto: str = "") -> None` — grava a situação e, se houver texto, uma `Mensagem` (autor `None` = aviso do sistema).
  - `Pedido.evento_aceito() -> bool` — contratei: S-2200 do `funcionario`; sair: S-2299 do `funcionario`; ferias: S-2230 da `ferias`; outros ou vínculo vazio: False.
  - `concluir_os_aceitos(pedidos: QuerySet) -> None` — para cada aprovado com `evento_aceito()`, `mudar("concluido", None, "O eSocial recebeu e aceitou.")`.
  - `Mensagem` (pedido, autor null, texto, criado_em; ordem por criado_em).
  - `Anexo` (pedido, arquivo `FileField(storage=_storage_privado, upload_to=…)`, nome, tipo_conteudo, tamanho, enviado_por, criado_em). Caminho: `anexos/pedido_<id>/<uuid>.<ext>` (nunca o nome que a pessoa mandou).
  - `portal/anexos.py`: `MAX_BYTES = 5 * 1024 * 1024`; `tipo_do_arquivo(arquivo) -> str` (content type) levanta `ValidationError` ("O arquivo passa de 5 MB…" / "Envie foto (JPG ou PNG) ou PDF."); `anexar(pedido, arquivo, por) -> Anexo`.

- [ ] **Step 1: testes** `test_mudar_grava_aviso_na_conversa`, `test_tipo_do_arquivo_aceita_pdf_jpg_png`, `test_recusa_executavel_com_nome_de_pdf`, `test_recusa_maior_que_5mb`, `test_anexo_fica_no_banco_com_nome_seguro` (com `BancoStorage`: `ArquivoPrivado` criado, nome começa com `anexos/pedido_`, não contém o nome original), `test_concluir_os_aceitos` (Evento S-2200 aceito do funcionário → concluído; rejeitado → continua aprovado).
- [ ] **Step 2:** rodar `manage.py test portal.tests.test_pedido_modelos` → FAIL (import).
- [ ] **Step 3:** implementar modelos, `anexos.py`, `makemigrations portal -n pedidos`.
- [ ] **Step 4:** rodar de novo → PASS.
- [ ] **Step 5:** commit "Portal: modelos de pedido, conversa e anexo".

### Task 2: Formulários dos seis pedidos

**Files:**
- Create: `portal/pedido_forms.py`, `portal/tests/test_pedido_forms.py`

**Interfaces:**
- Consumes: `tipo_do_arquivo` (Task 1).
- Produces:
  - `PedidoForm(forms.Form)` base: `__init__(*a, empresa, **kw)`; campo `arquivo` opcional validado por `tipo_do_arquivo`; campo `funcionario` (quando existe) só com pessoas ativas da `empresa`; `respostas() -> dict` serializável em JSON (datas ISO, Decimal em texto, funcionário fora: vai para a FK).
  - `ContrateiForm` (nome, cpf, data_nascimento, telefone, email, cep, salario, horario, vale_transporte, funcao, data_inicio, arquivo "Fotos dos documentos"); `SairForm` (funcionario, ultimo_dia, quem_pediu: pessoa/empresa/acordo/fim_contrato/justa_causa com o rótulo "Justa causa (fale com o escritório antes)", aviso: trabalha/nao_trabalha/nao_sei, observacao); `FeriasPedidoForm` (funcionario, inicio ≥ hoje, dias 5–30, vender_10; dias + 10 ≤ 30); `AlterarForm` (funcionario, cep, endereco, telefone, salario, cargo, banco_pix, a_partir_de, observacao; exige ao menos uma mudança); `DocumentoForm` (assunto: atestado/exame/documento_pessoal/outro, descricao, arquivo obrigatório); `DuvidaForm` (texto).
  - `FORMULARIOS: dict[str, type[PedidoForm]]` por tipo; `MensagemForm` (texto, arquivo; exige um dos dois).
  - `resumo(pedido) -> list[tuple[str, str]]`: rótulo e valor legível (escolha → rótulo, data → dd/mm/aaaa, Decimal → `moeda`, booleano → Sim/Não), sem campos vazios nem o funcionário.

- [ ] **Step 1: testes** `test_pessoa_de_outra_empresa_e_recusada`, `test_ferias_no_passado_e_recusada`, `test_alterar_sem_nenhuma_mudanca_e_recusado`, `test_documento_exige_arquivo`, `test_respostas_vao_para_json` (`json.dumps` não falha; `"salario": "2500.00"`, `"data_inicio": "2026-12-01"`), `test_resumo_mostra_rotulos_simples`.
- [ ] **Step 2:** rodar → FAIL. **Step 3:** implementar. **Step 4:** rodar → PASS.
- [ ] **Step 5:** commit "Portal: formulários dos pedidos".

### Task 3: Telas da dona

**Files:**
- Create: `portal/pedidos.py` (views), `templates/portal/pedidos.html`, `pedido_novo.html`, `pedido_form.html`, `pedido.html`, `_conversa.html`, `portal/tests/test_pedidos_dona.py`
- Modify: `portal/urls.py`, `templates/portal/base.html` (links Início · Pedidos), `templates/portal/inicio.html` (botões "Fazer um pedido"; em análise: "Mandar documento")

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces (nomes de URL `portal:`): `pedidos` (`cliente/pedidos/`), `pedido_novo` (`cliente/pedidos/novo/`), `pedido_criar` (`cliente/pedidos/novo/<tipo>/`), `pedido` (`cliente/pedidos/<pk>/`, POST = mensagem), `pedido_corrigir` (`…/<pk>/corrigir/`, só devolvido), `pedido_cancelar` (POST, só aberto), `pedido_anexo` (`…/<pk>/anexos/<anexo>/`).
- Todas as consultas: `Pedido.objects.filter(empresa=request.empresa)`; staff que abre `/cliente/pedidos/` vai para `escritorio_pedidos`.
- `tipos_permitidos(empresa) -> list[str]`: ativa → todos; senão documento e duvida.

- [ ] **Step 1: testes** `test_contratei_nao_mexe_em_funcionario_nem_esocial` (Funcionario e Evento com a mesma contagem; Pedido "enviado" com respostas), `test_anexo_do_pedido_e_baixado_so_pela_dona_da_empresa`, `test_empresa_em_analise_so_documento_e_duvida` (GET `novo/ferias/` → 404), `test_devolvido_mensagem_reenvia`, `test_corrigir_so_quando_devolvido`, `test_cancelar_so_aberto`, `test_isolamento_404_em_todas_as_rotas` (dona A com pedido e anexo de B: detalhe, corrigir, cancelar, anexo → 404), `test_lista_so_da_empresa`.
- [ ] **Step 2:** rodar → FAIL. **Step 3:** implementar views, URLs e telas (celular primeiro, `_campo.html`). **Step 4:** rodar → PASS.
- [ ] **Step 5:** commit "Portal: a dona faz pedidos, conversa e manda anexos".

### Task 4: Fila do escritório

**Files:**
- Create: `portal/escritorio.py`, `templates/pedidos/lista.html`, `templates/pedidos/detalhe.html`, `portal/tests/test_pedidos_escritorio.py`
- Modify: `portal/urls.py`, `templates/base.html` (item "Pedidos" com contador), `empresas/context_processors.py` (`pedidos_para_ver`: enviados, só staff)

**Interfaces:**
- Produces (URL `portal:`): `escritorio_pedidos` (`pedidos/`, abertos + aprovados por padrão, `?ver=todos`; topo com empresas em análise → `empresas:validar`), `escritorio_pedido` (`pedidos/<pk>/`; GET de enviado → em_analise; POST `acao=responder|devolver|cancelar`, devolver/cancelar exigem texto), `escritorio_aprovar` (`pedidos/<pk>/aprovar/`, POST, só aberto: documento/duvida → concluído; outros → `session["empresa_id"] = pedido.empresa_id` e redireciona ao formulário técnico com `?pedido=<pk>`; empresa inativa ou "alterar" sem funcionário → mensagem de erro), `escritorio_anexo`.
- `DESTINO = {"contratei": "pessoal:novo", "ferias": "folha:ferias_nova", "sair": "folha:rescisao_nova", "alterar": "pessoal:editar"}`.

- [ ] **Step 1: testes** `test_dona_nao_abre_a_fila` (GET → /cliente/, POST → 403), `test_abrir_poe_em_analise`, `test_devolver_exige_texto`, `test_concluir_documento`, `test_aprovar_troca_empresa_e_abre_formulario` (redireciona para `/funcionarios/novo/?pedido=<pk>` e a sessão fica com a empresa do pedido), `test_pedido_fechado_nao_aprova` (404), `test_menu_mostra_contador`.
- [ ] **Step 2:** rodar → FAIL. **Step 3:** implementar. **Step 4:** rodar → PASS.
- [ ] **Step 5:** commit "Pedidos: fila do escritório".

### Task 5: Aprovar pelo formulário técnico

**Files:**
- Create: `portal/aprovacao.py`, `templates/portal/_pedido_resumo.html`, `portal/tests/test_pedidos_aprovacao.py`
- Modify: `pessoal/views.py` (`FuncionarioCreateView`, `FuncionarioUpdateView`), `folha/views.py` (`ferias_nova`, `rescisao_nova`), `templates/form.html`, `templates/folha/ferias_form.html`, `templates/folha/rescisao_form.html` (incluem o resumo quando há `pedido`)

**Interfaces:**
- Consumes: `Pedido`, `resumo` (Tasks 1–2).
- Produces:
  - `pedido_em_aberto(request, tipo: str, **filtros) -> Pedido | None` — só staff, `?pedido` numérico, `empresa=request.empresa`, situação aberta.
  - `iniciais(pedido) -> dict` para o formulário técnico: contratei → nome, cpf, data_nascimento, telefone, email, cep, salario, data_admissao, descricao_jornada; sair → funcionario, data_desligamento, motivo (pessoa 07, empresa 02, acordo 33, fim_contrato 06, justa_causa 01), tipo_aviso (fim_contrato/justa_causa → nenhum; trabalha → trabalhado; nao_trabalha → indenizado, ou dispensado se a pessoa pediu); ferias → funcionario, aquisitivo do `proximo_periodo_aquisitivo`, inicio, dias, dias_abono (10 se vender); alterar → cep, telefone, salario quando preenchidos.
  - `aprovar(pedido, por, **vinculo) -> None` — grava o vínculo, situação aprovado (alterar → concluído) e aviso na conversa.

- [ ] **Step 1: testes** `test_contratei_preenche_e_aprova_ao_salvar` (GET mostra o nome; POST válido → Pedido aprovado com `funcionario`), `test_pedido_de_outra_empresa_nao_aprova` (sessão em A, `?pedido` de B → nada muda), `test_ferias_aprova_com_vinculo`, `test_rescisao_aprova_com_vinculo`, `test_alterar_conclui`, `test_lista_conclui_quando_evento_aceito`.
- [ ] **Step 2:** rodar → FAIL. **Step 3:** implementar. **Step 4:** rodar → PASS.
- [ ] **Step 5:** commit "Pedidos: aprovar abre o formulário técnico preenchido".

### Task 6: Fechamento

- [ ] Suíte completa `manage.py test` verde; `makemigrations --check` sem mudanças.
- [ ] Revisão do branch inteiro; corrigir Critical/Important com teste.
- [ ] Push, PR pelo Chrome, merge (instrução do dono: "No fim de cada etapa, crie o PR e faça o merge").
- [ ] Conferir no site publicado: `/cliente/pedidos/` → login; `/pedidos/` → login; páginas públicas 200.
