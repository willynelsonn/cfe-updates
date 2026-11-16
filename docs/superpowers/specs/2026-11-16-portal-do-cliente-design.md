# Portal do cliente: desenho

Data: 16/11/2026 · Desenho visual (5 telas de celular): https://claude.ai/artifact/2ewP5Uk4cHsogi9XmF59cM

## Por que

O escritório W. Neves faz a folha das empresas clientes no FolhaWeb. Hoje só o escritório entra no site, e as telas
falam a língua do contador (FPAS, RAT, rubricas, competência). O dono quer que **qualquer empresa possa se cadastrar
sozinha** e que **a dona da empresa, sem saber nada de folha, faça tudo pelo celular**: contratar, desligar, dar férias,
mandar documento, aprovar a folha e pagar as guias. **Tudo o que a dona fizer passa pela validação do escritório antes de
valer** (antes de ir ao eSocial). A folha continua sendo feita pelo escritório.

## Quem usa

- **Escritório** (hoje: o dono do FolhaWeb): usa as telas atuais e uma tela nova, "Pedidos", para validar o que as
  clientes mandam.
- **Dona da empresa cliente**: usa só o portal (`/cliente/`), no celular, em linguagem simples. Vê só a própria empresa.
  Funcionários das clientes **não** entram (decidido pelo dono).

## Objetivos

1. Cadastro aberto: a dona cria a conta e cadastra a empresa; o escritório confere e libera.
2. Convite: para clientes que já existem (ex.: ANA FLAVIA), o escritório gera um link para a dona criar a senha.
3. Portal com as telas do desenho: Início, Equipe, Pagamentos (guias e holerites), Aprovar a folha, Falar com o escritório.
4. Pedidos: contratei alguém, alguém vai sair, férias, alterar dados de alguém, mandar documento, dúvida. Cada pedido
   vai para a fila do escritório, que confere, completa a parte técnica e só então o sistema envia ao eSocial.
5. Ajuda em toda palavra técnica: botões "O que é?" e "Como preencher?".

## Não-objetivos (nesta versão)

- Acesso de funcionários das clientes (holerite pelo próprio funcionário).
- A dona fazer a folha sem o escritório (isso é o TranquiloMEI).
- Aviso por e-mail ou WhatsApp automático (fase 4; precisa de um serviço de e-mail configurado).
- Cobrança/mensalidade do escritório dentro do site.

## Antiobjetivos (falhou mesmo que funcione)

- Uma cliente ver qualquer dado de outra empresa, por qualquer endereço do site.
- Algo que a cliente fez chegar ao eSocial sem o escritório validar.
- Palavra técnica sem explicação nas telas da cliente.
- Dado real de cliente ou funcionário no repositório (ele é público).

## Abordagens consideradas

| | Como | Troca | Decisão |
|---|---|---|---|
| **A** | Portal como área nova do próprio FolhaWeb (`/cliente/`), mesmo banco e mesma publicação | Reaproveita cálculo, holerite, guias e eSocial; exige regras de acesso rígidas no mesmo código | **Escolhida** (o dono descreveu exatamente isso: escritório faz a folha, cliente usa o portal) |
| B | Site ou app separado conversando com o FolhaWeb | Mais liberdade visual; dobra o trabalho (dois logins, ponte, duas publicações) | Descartada: não compensa |
| C | Reaproveitar as telas do escritório escondendo menus | Rápido; continua técnico | Descartada: vai contra o objetivo |

## Como funciona

### 1. Cadastro aberto (página pública `/cadastro/`)

- A dona informa: nome, CPF, e-mail, celular, senha; CNPJ da empresa; quantas pessoas tem registradas; aceite dos
  Termos de uso e da Política de privacidade (obrigatório, com data, hora e versão guardadas).
- O CNPJ é validado (dígitos) e consultado em fonte pública (BrasilAPI) para preencher razão social, CNAE e município.
  Se a consulta falhar, ela digita.
- CNPJ que já existe no sistema: mensagem neutra ("Essa empresa já tem cadastro. Fale com o escritório."), sem revelar
  nada da empresa.
- Proteção: limite de tentativas por IP (mesmo mecanismo do login), campo-armadilha contra robôs, regras de senha do
  Django.
- Resultado: usuário (não é escritório) + empresa com situação **"em análise"** (fora das listas do escritório e do
  envio automático) + vínculo dona↔empresa.
- Enquanto está em análise, a dona entra e vê só: "Recebemos seu cadastro", o que falta (ex.: procuração no e-CAC para
  o CNPJ do escritório, com passo a passo) e um botão para mandar documentos.

### 2. Validação da empresa pelo escritório

- Na tela "Pedidos" do escritório aparece "Nova empresa para conferir". O escritório abre o cadastro técnico já
  existente (classificação tributária, FPAS, RAT, sindicato…) preenchido com o que veio, completa e clica
  **Liberar** ou **Recusar (com motivo)**.
- Liberada: empresa ativa, transmissor = escritório, envio automático **desligado** até haver certificado.
  A dona passa a ver o portal completo.

### 3. Convite para clientes que já existem

- Na lista de empresas, botão "Convidar a dona": gera um link de uso único, válido por 7 dias, no padrão do
  "esqueci a senha" do Django. O escritório manda o link pelo WhatsApp; a dona cria a senha e aceita os termos.

### 4. Pedidos (tudo o que a dona faz)

Fluxo de cada pedido: **Enviado → Em análise → (Devolvido para corrigir ↺) → Aprovado e enviado ao governo → Concluído**,
ou **Cancelado**. A dona vê essa linha do tempo; cada pedido tem uma conversa (mensagens dos dois lados).

| Pedido | A dona responde (linguagem simples, um passo por tela) | O escritório, ao aprovar |
|---|---|---|
| Contratei alguém | Pessoa (nome, CPF, nascimento, contato, CEP), salário, dias e horário, vale-transporte, o que ela vai fazer, data de início, fotos dos documentos; vê o custo estimado (lógica do simulador já existente) | Abre "Novo funcionário" já preenchido, completa categoria, cargo/CBO, código IBGE, jornada; ao salvar, o fluxo atual gera o S-2200 |
| Alguém vai sair | Quem, último dia, quem pediu (a pessoa / a empresa / acordo / fim de contrato), aviso trabalhado ou não, observação; "justa causa" mostra "fale com o escritório antes" | Abre a rescisão já preenchida; fluxo atual calcula e envia |
| Férias | Quem, primeiro dia, quantos dias, se quer vender 10 dias; o portal mostra o direito ("tem 30 dias desde 01/03") e avisa os prazos (avisar 30 dias antes; pagar até 2 dias antes) | Abre "Nova férias" preenchida; fluxo atual |
| Alterar dados de alguém | Novo endereço, telefone, salário, cargo, dados de banco/Pix | Edita o funcionário; o sistema envia S-2205 (dados pessoais) ou S-2206 (salário, cargo, jornada). **Esses dois eventos ainda não existem no FolhaWeb** (hoje há S-1000, S-1005, S-1010, S-1020, S-1200, S-1210, S-1299, S-2200, S-2230, S-2299) e entram na fase 3. Banco/Pix não vai ao eSocial |
| Mandar documento | Foto ou PDF + do que se trata (atestado, exame, etc.) | Arquiva; nada vai ao governo |
| Dúvida | Texto | Responde na conversa |

Regras:
- **Nada do pedido toca as tabelas de funcionário, férias ou rescisão antes da aprovação.** As respostas ficam guardadas
  no próprio pedido; por isso o envio automático ao eSocial não dispara cedo.
- Aprovar = o escritório salva o formulário técnico atual, aberto com `?pedido=<id>`. Ao salvar com sucesso, o pedido
  guarda o vínculo com o que foi criado e muda para "Aprovado". "Concluído" vem do evento do eSocial aceito.
- Anexos ficam no armazenamento privado já usado para certificados (no banco), visíveis só ao escritório e à dona
  daquela empresa.

### 5. Folha do mês

- O escritório calcula como hoje. Folha calculada aparece no portal como "Precisa de você: aprovar a folha".
- A dona vê o total que sai da conta, quanto cada pessoa recebe e o desconto de cada uma; **Aprovar** ou **Tenho uma
  dúvida ou mudança** (vira pedido "Dúvida" ligado àquela folha).
- Recalcular a folha apaga a aprovação.
- O escritório pode fechar sem a aprovação, com um aviso pedindo confirmação.

### 6. Pagamentos, holerites e equipe

- Pagamentos: guias da empresa com valor e vencimento; "Baixar PDF" quando a guia estiver emitida; "Já paguei" (a dona
  marca; o escritório vê). "Copiar código de barras/Pix" só depois que o sistema guardar essa linha (hoje guarda só o
  PDF e o número do documento); até lá, o botão não aparece.
- Salários: líquido de cada pessoa com o Pix ou banco cadastrado.
- Holerites: lista por mês, para baixar.
- Equipe: quem trabalha, cargo, desde quando, salário; de cada pessoa saem os pedidos (férias, sair, alterar dados).

### 7. Ajuda "O que é?" e "Como preencher?"

- Um dicionário único de termos (título, o que é, como preencher, por que importa) usado pelo portal; depois, pelas
  telas do escritório (fase 4).
- Texto revisado pelo escritório antes de publicar (é orientação legal).

## Segurança (obrigatório; cada item com teste)

1. **Escritório = `is_staff`.** Cliente = usuário sem `is_staff` com vínculo a uma ou mais empresas.
2. **Bloqueio por padrão:** um middleware só deixa a cliente acessar `/cliente/…`, `/sair/`, `/conta/…`,
   `/static/…` e as páginas públicas. Qualquer outra rota: GET vai para `/cliente/`, POST recebe 403. Rotas novas do
   escritório ficam protegidas sem precisar lembrar.
3. **Empresa ativa da cliente** sai só dos vínculos dela. Hoje o middleware cai na "primeira empresa ativa" quando a
   sessão não tem empresa; para cliente isso é proibido.
4. Toda consulta do portal filtra pela empresa da cliente; objeto de outra empresa = 404 (não 403, para não confirmar
   que existe).
5. Testes de isolamento: duas empresas, duas donas; cada URL do portal com IDs da outra empresa → 404; cada URL do
   escritório acessada pela dona → bloqueada.
6. Senhas e tokens nunca no repositório; o link de convite expira e é de uso único.

## Dados novos

- `Acesso`: usuário, empresa, termos aceitos em, versão dos termos (único por usuário+empresa).
- `Empresa.situacao`: em análise / ativa / recusada, + motivo da recusa e quem validou, quando.
- `Pedido`: empresa, quem criou, tipo, situação, respostas (JSON), vínculos opcionais (funcionário, férias, rescisão,
  folha), datas.
- `Mensagem`: pedido, autor, texto, data.
- `Anexo`: pedido, arquivo (armazenamento privado), nome.
- `Competencia`: aprovada em / aprovada por.
- Migrações só adicionam; nada existente muda de significado.

## Restrições

- **Render grátis "dorme"**: a primeira visita espera 30–60 s numa tela do Render. Antes de convidar clientes, passar
  para o plano pago mais barato.
- O envio ao eSocial continua dependendo do certificado A1 do escritório e da procuração de cada cliente. O portal
  funciona sem isso; os pedidos param em "Aprovado".
- Repositório público: testes só com dados inventados.
- Termos de uso e Política de privacidade: o construtor escreve um rascunho; o escritório revisa (responsabilidade legal).

## Fases (cada uma termina em PR + merge, com testes)

1. **Base**: acesso por empresa, bloqueio por padrão, cadastro aberto, convite, empresa em análise, validação pelo
   escritório, termos.
2. **Portal de leitura**: Início, Equipe, Pagamentos, Holerites, Aprovar a folha.
3. **Pedidos**: os 6 tipos, conversa, anexos, tela "Pedidos" do escritório, abrir formulário técnico preenchido,
   eventos S-2205 e S-2206.
4. **Acabamento**: "O que é?" nas telas do escritório, aviso por e-mail, convite automático por e-mail.

## Decisões minhas (confira)

- Escritório é quem tem `is_staff`; um futuro funcionário do escritório precisa dessa marca.
- Uma dona pode ter mais de uma empresa (aparece um seletor).
- O escritório pode fechar a folha sem a aprovação da cliente, com aviso.
- A dona pode marcar uma guia como paga.
- Sem e-mail na primeira versão; os avisos aparecem dentro do site.
- Valores mostrados à cliente antes do cálculo do escritório levam a palavra "estimativa".
- **Leitura de "fazer tudo depois de eu validar"**: cada pedido da dona é validado pelo escritório antes de valer.
  (A outra leitura, validar só o cadastro e depois a dona agir direto, ficaria como opção por empresa numa fase 5.)

## Fica para quem construir

- O mapeamento campo a campo de cada pedido para o formulário técnico.
- O texto final das ajudas e dos termos (para revisão do escritório).
- Detalhes visuais, seguindo o desenho e as cores do FolhaWeb.
