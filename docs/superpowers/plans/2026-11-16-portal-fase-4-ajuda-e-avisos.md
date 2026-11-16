# Portal do cliente, fase 4: "O que é?", avisos por e-mail e convite por e-mail — plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fase 4 do desenho ("Acabamento"): ajuda "O que é?" em toda palavra técnica dos formulários (escritório e
portal), aviso por e-mail quando algo muda num pedido, e convite da dona mandado por e-mail.

**Architecture:** Um dicionário único (`portal/ajuda.py`) liga o nome do campo ao termo; o `_campo.html`, usado por
todos os formulários, mostra o "O que é?" sozinho. Os avisos saem de `portal/avisos.py`, ligados por sinal ao criar
pedido e mensagem, depois do commit e sem nunca derrubar a tela. O e-mail só sai com SMTP configurado por variável de
ambiente; sem ela, nada é enviado nem gravado em log.

**Spec:** `docs/superpowers/specs/2026-11-16-portal-do-cliente-design.md` (seção 7, "Não-objetivos" e "Fases": fase 4).

## Decisões deste plano (rulings)

- O dicionário de termos não existia (nem no portal). Ele nasce aqui e serve aos dois lados, pelo nome do campo.
- O texto é um rascunho meu; o desenho pede revisão do escritório antes de valer como orientação. O PR e o módulo dizem isso.
- Um só botão "O que é?" (`<details>`) com "o que é", "como preencher" e "por que importa", sem JavaScript.
- E-mail: SMTP por `FOLHA_EMAIL_HOST`, `FOLHA_EMAIL_PORTA`, `FOLHA_EMAIL_USUARIO`, `FOLHA_EMAIL_SENHA`, `FOLHA_EMAIL_REMETENTE`.
  Sem `FOLHA_EMAIL_HOST`: backend "dummy" (não manda e não escreve o texto no log do Render).
- Quem recebe: dona = e-mails de quem tem `Acesso` à empresa; escritório = `FOLHA_ESCRITORIO_EMAIL` (vírgulas) ou,
  sem ela, os usuários `is_staff` ativos com e-mail.
- Avisos: pedido novo e mensagem da dona → escritório; mensagem do escritório ou aviso do sistema (aprovado, devolvido,
  concluído, cancelado) → dona; cadastro novo de empresa → escritório. Ninguém recebe aviso do que ele mesmo fez.
- Link no e-mail: `FOLHA_SITE_URL`, ou `RENDER_EXTERNAL_URL` (o Render preenche sozinho).
- Convite por e-mail: depois de gerar o link, a tela do convite tem "Mandar por e-mail". O código vai de volta no POST
  e é conferido (`Convite.pelo_codigo` + mesma empresa); só o escritório usa.

## Global Constraints

- Repositório público: só dados inventados.
- Escritório = `is_staff`; dona nunca vê nem dispara nada de outra empresa (404).
- Falha de e-mail nunca impede salvar o pedido ou a mensagem.

## Review Focus

1. SMTP fora do ar ou mal configurado: a tela continua funcionando.
2. Dona com duas empresas: aviso só da empresa do pedido.
3. Convite por e-mail com código de outra empresa, usado ou vencido: recusado.
4. Mensagem da própria dona não gera e-mail para ela.

---

### Task 1: Dicionário e "O que é?" nos formulários
- Create `portal/ajuda.py` (`TERMOS`, `CAMPOS`, `termo_do_campo(nome) -> dict | None`); tag `ajuda` em `folha/templatetags/ui.py`;
  `templates/_campo.html` mostra o `<details class="oque">`; CSS em `static/css/app.css`.
- Testes `portal/tests/test_ajuda.py`: todo `CAMPOS` aponta para um termo com os três textos; a tela de empresa do
  escritório mostra "O que é?" e o texto do FPAS; o pedido "Alguém vai sair" da dona mostra a ajuda do aviso prévio.

### Task 2: Avisos por e-mail
- `config/settings.py` (e-mail por variável), `portal/avisos.py`, `portal/apps.py` (liga os sinais), `portal/views.py` (cadastro).
- Testes `portal/tests/test_avisos.py` (com `mail.outbox` e `captureOnCommitCallbacks`): pedido novo → escritório;
  devolver → dona com link; mensagem da dona → só escritório; dona da outra empresa não recebe; erro de SMTP não
  derruba a tela; cadastro novo → escritório.

### Task 3: Convite por e-mail
- `empresas/views.py` (`convite_email`), `empresas/urls.py`, `templates/empresas/convite_link.html`.
- Testes: escritório manda → 1 e-mail com o link; código de outra empresa ou já usado → nada sai; dona → bloqueada.
