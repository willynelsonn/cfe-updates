# Portal do cliente, fase 3: alterações no eSocial (S-2205 e S-2206) e custo estimado — plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar a fase 3 do desenho: mudar dados de alguém (pelo escritório ou por pedido da dona) gera o S-2205
(dados pessoais) ou o S-2206 (contrato) no eSocial, o pedido "Alterar dados" só conclui quando o eSocial aceita, e a
dona vê o custo estimado ao pedir "Contratei alguém".

**Architecture:** Os XMLs novos ficam em `esocial/xml_eventos.py` reaproveitando os pedaços do S-2200; a decisão
"o que mudou → qual evento" fica em `esocial/servico.py` (`gerar_alteracoes`); a tela "Editar funcionário" chama essa
função ao salvar, como o "Novo funcionário" já chama `gerar_admissao`. O pedido guarda as chaves dos eventos gerados e
conclui quando o último evento de cada chave está aceito.

**Tech Stack:** Django 5.2, lxml (XSD), SQLite nos testes.

**Spec:** `docs/superpowers/specs/2026-11-16-portal-do-cliente-design.md` (seção 4, linha "Alterar dados de alguém" e
"Contratei alguém"; fase 3 em "Fases").

## Decisões deste plano (rulings)

- A fase 2 (PR #16) já entregou os pedidos, a conversa, os anexos e a fila do escritório (o desenho chama isso de fase 3).
  Esta fase entrega o que faltou da fase 3 do desenho: S-2205, S-2206 e o custo estimado do "Contratei".
- Esquemas: o pacote oficial em produção hoje é "Esquemas XSD v. S-1.3 (até NT 07/2026 rev.), produção em 26/10/2026"
  (`2026-10-26_esquemas_xsd_v_s_01_03_00-1-1.zip`, gov.br/esocial). Os novos `evtAltCadastral.xsd` e
  `evtAltContratual.xsd` dependem do `tipos.xsd` desse pacote, então todos os esquemas usados passam para essa versão.
- O S-2205/S-2206 sai de qualquer edição do funcionário (não só de pedido), com o mesmo critério do S-2200:
  só com `envio_automatico` ligado.
- Admissão (S-2200) ainda não transmitida (pendente, erro, rejeitada): em vez de S-2205/S-2206, gera de novo o S-2200
  com os dados novos. Sem S-2200 e sem `esocial_ja_cadastrado`: nada é gerado (a admissão nunca foi ao eSocial).
- Problema de dado que o eSocial recusaria (raça/cor "Não informado" no S-2205; empresa sem CNPJ do sindicato no
  S-2206) não impede salvar: o evento entra na fila com situação "erro" e a mensagem explica o que corrigir; o botão
  "Gerar de novo" (`regerar`) refaz com os dados atuais. Assim nenhuma mudança se perde.
- Mesma chave já aceita no eSocial (duas mudanças com a mesma data): o novo evento vai como retificação
  (`indRetif=2` + `nrRecibo`).
- `tmpParc` (S-2200 e S-2206): o código 1 só vale para doméstico (104). Até 25 h de doméstico = 1; até 30 h dos demais
  = 2; acima disso = 0. Corrige o S-2200, que mandava 1 para qualquer jornada de até 30 h.
- Custo estimado: `custo_mensal` sem vale-transporte (o pedido só diz se usa VT, não o valor), sempre com a palavra
  "estimativa".

## Global Constraints

- Repositório público: testes só com dados inventados.
- Nada do pedido toca funcionário, férias ou rescisão antes de o escritório salvar o formulário técnico.
- Toda consulta do portal filtra pela empresa da dona; objeto de outra empresa = 404.
- Migrações só adicionam.
- Valores mostrados à cliente antes do cálculo do escritório levam a palavra "estimativa".

## Review Focus

1. Duas mudanças no mesmo dia, a primeira já aceita: a segunda precisa ir como retificação, senão o eSocial recusa.
2. Edição que não muda nada que vai ao eSocial (só Pix, banco, VT): nenhum evento, pedido conclui na hora.
3. Funcionário com S-2200 ainda na fila: não pode sair S-2205/S-2206 antes da admissão.
4. Pedido de outra empresa aberto com `?pedido=` na edição: não aprova nem guarda chaves (já coberto na fase 2).
5. Endpoint do custo chamado por empresa em análise ou pelo escritório: 404 / redireciona.

---

### Task 1: Esquemas atuais e XMLs do S-2205 e S-2206

**Files:**
- Modify: `esocial/schemas/v_S_01_03_00/*.xsd` (troca pelo pacote de 26/10/2026) + Create `evtAltCadastral.xsd`, `evtAltContratual.xsd`
- Modify: `esocial/xml_eventos.py`
- Test: `esocial/tests/test_alteracoes.py`

**Interfaces:**
- Produces: `EVENTOS["S-2205"] = ("evtAltCadastral", 2)`, `EVENTOS["S-2206"] = ("evtAltContratual", 2)`;
  `s2205(funcionario, data: date, recibo: str = "") -> (id, root)`; `s2206(funcionario, data: date, recibo: str = "") -> (id, root)`;
  `_ide_evento(..., recibo="")` (com recibo: `indRetif=2` + `nrRecibo`).

- [ ] Testes: `test_s2205_valido_no_xsd` (com dependente; `<dtAlteracao>`, `<nmTrab>`, `<paisNac>105</paisNac>`),
  `test_s2206_valido_no_xsd` (`<vrSalFx>`, `<nmCargo>`, `<tmpParc>0</tmpParc>`), `test_retificacao_leva_recibo`
  (`<indRetif>2</indRetif>` e `<nrRecibo>`), `test_tmp_parc` (20 h, categoria 101 → 2; 20 h, 104 → 1; 44 h → 0).
  Validar com `validar_evento(tipo, xml, assinado=False) == []`.
- [ ] Rodar: falham (S-2205 não existe).
- [ ] Copiar os esquemas do pacote; extrair do `s2200` os pedaços comuns (dados pessoais, endereço/dependentes/contato,
  `infoContrato`) e escrever `s2205`/`s2206`.
- [ ] Rodar `manage.py test esocial` → tudo verde (os eventos antigos continuam válidos no esquema novo).
- [ ] Commit.

### Task 2: Gerar as alterações a partir do que mudou

**Files:**
- Modify: `esocial/servico.py`
- Test: `esocial/tests/test_alteracoes.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `CAMPOS_S2205`, `CAMPOS_S2206` (conjuntos de nomes de campo de `Funcionario`);
  `gerar_alteracoes(funcionario, campos: set[str], data: date) -> list[Evento]`;
  `gerar_alteracao_cadastral(f, data) -> Evento`; `gerar_alteracao_contratual(f, data) -> Evento`;
  chaves `S-2205:func:<pk>:<AAAA-MM-DD>` e `S-2206:func:<pk>:<AAAA-MM-DD>`; `regerar` aceita S-2205/S-2206.

- [ ] Testes: só `chave_pix`/`banco` → `[]`; `salario` → um S-2206 pendente com `depende == [chave_admissao]`
  quando o S-2200 está aceito; `logradouro` → S-2205; os dois → dois eventos; S-2200 pendente → `[S-2200 novo]`;
  sem S-2200 e sem `esocial_ja_cadastrado` → `[]`; `esocial_ja_cadastrado` → evento sem dependências;
  `raca_cor=6` → S-2205 com `status == "erro"` e mensagem "Raça/cor"; `regerar` de S-2205 com erro depois de corrigir →
  pendente; mesma chave aceita → retificação com o recibo.
- [ ] Rodar: falham.
- [ ] Implementar (`_registrar(..., problemas=())`).
- [ ] Rodar `manage.py test esocial` → verde. Commit.

### Task 3: Editar funcionário manda ao eSocial; pedido "Alterar" conclui com o aceite

**Files:**
- Modify: `pessoal/forms.py` (campo `alteracao_em` só na edição), `pessoal/views.py` (`FuncionarioUpdateView.form_valid`)
- Modify: `portal/models.py` (`Pedido.eventos_esocial = JSONField(default=list, blank=True)`, `evento_aceito` para "alterar"),
  migração `portal/migrations/0002_pedido_eventos_esocial.py`
- Modify: `portal/aprovacao.py` (`iniciais` leva `a_partir_de` → `alteracao_em`; `aprovar(request, pedido, eventos=None, **vinculo)`;
  `PedidoMixin.aprovar_pedido(eventos=None)`)
- Test: `portal/tests/test_pedidos_aprovacao.py`, `pessoal/tests/` (edição)

**Interfaces:**
- Consumes: `gerar_alteracoes` (Task 2).

- [ ] Testes: editar salário com envio automático → S-2206 na fila com `dtAlteracao` = `alteracao_em`;
  envio desligado → nenhum evento; `alteracao_em` antes da admissão → erro no formulário;
  pedido "alterar" com salário → `aprovado` e `eventos_esocial == [chave]`; evento aceito → lista da dona mostra
  "Concluído"; pedido só com Pix → `concluido`; `?pedido=` com `a_partir_de` preenche `alteracao_em`.
- [ ] Rodar: falham.
- [ ] Implementar.
- [ ] Rodar a suíte inteira → verde. Commit.

### Task 4: Custo estimado no "Contratei alguém"

**Files:**
- Modify: `portal/pedidos.py` (view `custo`), `portal/urls.py` (`cliente/pedidos/custo/` → `pedido_custo`),
  `portal/pedido_forms.py` (`resumo` do "contratei" ganha a linha do custo),
  `templates/portal/pedido_form.html` (caixa + script só no "contratei"), Create `templates/portal/_custo.html`
- Test: `portal/tests/test_pedidos_dona.py`

- [ ] Testes: dona de empresa ativa, `?salario=2500,00` → 200 com "estimativa" e o total de `custo_mensal`;
  salário inválido → resposta vazia; empresa em análise → 404; escritório → não vê (redireciona);
  página do pedido "contratei" mostra "Custo estimado".
- [ ] Rodar: falham. Implementar. Rodar a suíte inteira → verde. Commit.
