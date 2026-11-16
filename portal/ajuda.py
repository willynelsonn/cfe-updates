"""Dicionário único dos termos técnicos: "O que é?", "Como preencher?" e "Por que importa".

Usado pelo portal da dona e pelas telas do escritório, pelo nome do campo do formulário (``CAMPOS``).
RASCUNHO: o texto é orientação legal e precisa da revisão do escritório (desenho do portal, seção 7).
"""

TERMOS = {
    "class_trib": {
        "titulo": "Classificação tributária",
        "o_que_e": "Código do eSocial que diz como a empresa paga impostos: Simples Nacional, lucro presumido, lucro real e outros.",
        "como_preencher": "Simples Nacional: 01 (ou 03 se tiver atividade do Anexo IV). Lucro presumido ou real: 99. Confira no cartão CNPJ e no contrato social.",
        "por_que": "Decide se a empresa recolhe a contribuição patronal sobre a folha. Errado, a DCTFWeb sai com valor errado.",
    },
    "simples_anexo_iv": {
        "titulo": "Simples Nacional, Anexo IV",
        "o_que_e": "Atividades do Simples (como construção, limpeza e vigilância) que pagam o INSS patronal à parte, fora do DAS.",
        "como_preencher": "Marque só se a atividade principal estiver no Anexo IV da LC 123/2006.",
        "por_que": "Muda o custo da folha: com Anexo IV entram 20% de INSS patronal e o RAT.",
    },
    "cnae": {
        "titulo": "CNAE",
        "o_que_e": "Código da atividade econômica da empresa, o mesmo do cartão CNPJ.",
        "como_preencher": "Os 7 números da atividade principal (ex.: 4711-3/02). Está no cartão CNPJ da Receita.",
        "por_que": "Define o grau de risco (RAT) e entra no cadastro do estabelecimento no eSocial.",
    },
    "fpas": {
        "titulo": "FPAS",
        "o_que_e": "Código do Fundo de Previdência e Assistência Social, que diz para quais entidades (SESC, SENAC, SEBRAE...) a empresa contribui.",
        "como_preencher": "Comércio costuma ser 515; indústria, 507. Confira na tabela 4 do eSocial pela atividade da empresa.",
        "por_que": "Define a alíquota de terceiros que entra na guia do INSS.",
    },
    "cod_terceiros": {
        "titulo": "Código de terceiros",
        "o_que_e": "Combinação das entidades (SESC, SENAI, INCRA, salário-educação...) para as quais a empresa recolhe junto com o INSS.",
        "como_preencher": "Vem junto com o FPAS na tabela 4 do eSocial (ex.: FPAS 515 com código 0115).",
        "por_que": "Errado, a guia de terceiros sai com valor errado.",
    },
    "aliq_terceiros": {
        "titulo": "Alíquota de terceiros",
        "o_que_e": "Percentual somado das entidades de terceiros sobre a folha.",
        "como_preencher": "Some as alíquotas do código de terceiros (ex.: 5,8% no comércio). Empresa do Simples não paga.",
        "por_que": "Entra no custo da folha e na guia do INSS.",
    },
    "rat": {
        "titulo": "RAT",
        "o_que_e": "Riscos Ambientais do Trabalho: contribuição de 1%, 2% ou 3% conforme o risco de acidente da atividade.",
        "como_preencher": "Veja a alíquota do CNAE principal no Anexo V do Decreto 3.048/1999.",
        "por_que": "Multiplicado pelo FAP, vira o percentual que a empresa paga sobre a folha para cobrir acidentes.",
    },
    "fap": {
        "titulo": "FAP",
        "o_que_e": "Fator Acidentário de Prevenção: número de 0,5 a 2,0 que aumenta ou diminui o RAT conforme os acidentes da empresa.",
        "como_preencher": "Consulte no site do FAP (Previdência) com o CNPJ. Sem consulta, use 1,0000.",
        "por_que": "Empresa com poucos acidentes paga menos; com muitos, paga mais.",
    },
    "sindicato": {
        "titulo": "CNPJ do sindicato",
        "o_que_e": "Sindicato da categoria dos empregados da empresa.",
        "como_preencher": "O CNPJ do sindicato que assina a convenção coletiva da atividade. Pergunte ao escritório se não souber.",
        "por_que": "É obrigatório na admissão (S-2200) e na alteração de contrato (S-2206) no eSocial.",
    },
    "inicio_esocial": {
        "titulo": "Início no eSocial",
        "o_que_e": "Mês a partir do qual os dados da empresa valem no eSocial.",
        "como_preencher": "Ano e mês no formato AAAA-MM (ex.: 2026-01).",
        "por_que": "Os eventos de tabela (empresa, rubricas, lotação) são enviados com essa data de início.",
    },
    "ambiente": {
        "titulo": "Ambiente do eSocial",
        "o_que_e": "Produção é o eSocial de verdade; produção restrita é o ambiente de testes do governo.",
        "como_preencher": "Use produção restrita para testar. Só mude para produção quando tudo estiver conferido.",
        "por_que": "O que vai para produção vale de verdade e só sai com retificação ou exclusão.",
    },
    "transmissor": {
        "titulo": "Transmissor",
        "o_que_e": "CNPJ de quem assina e envia os eventos (normalmente o escritório, com procuração da empresa).",
        "como_preencher": "O CNPJ do escritório dono do certificado digital.",
        "por_que": "Sem procuração no e-CAC para esse CNPJ, o eSocial recusa os envios.",
    },
    "envio_automatico": {
        "titulo": "Envio automático",
        "o_que_e": "Faz o sistema gerar e mandar os eventos ao eSocial sozinho ao salvar admissões, férias, desligamentos e alterações.",
        "como_preencher": "Ligue só depois de cadastrar o certificado digital da empresa.",
        "por_que": "Desligado, nada vai ao governo até alguém mandar pela tela do eSocial.",
    },
    "ja_iniciado": {
        "titulo": "Já cadastrado por outro sistema",
        "o_que_e": "Indica que o eSocial já recebeu esse cadastro por outro programa (ex.: Domínio).",
        "como_preencher": "Marque só se o cadastro já foi aceito no eSocial por outro sistema.",
        "por_que": "Evita mandar de novo o que já existe, o que o eSocial recusaria.",
    },
    "categoria": {
        "titulo": "Categoria do trabalhador",
        "o_que_e": "Código do eSocial para o tipo de vínculo: empregado comum, aprendiz, doméstico, intermitente...",
        "como_preencher": "Quase sempre 101 (empregado geral). Aprendiz é 103; doméstico, 104.",
        "por_que": "Muda FGTS, regras de jornada e o que o eSocial exige.",
    },
    "cbo": {
        "titulo": "Cargo e CBO",
        "o_que_e": "O CBO é o código oficial da ocupação (Classificação Brasileira de Ocupações).",
        "como_preencher": "Procure a ocupação no site do CBO (mtecbo.gov.br) e use os 6 números (ex.: 848305 padeiro).",
        "por_que": "Vai no contrato do eSocial e em estatísticas do governo.",
    },
    "jornada": {
        "titulo": "Jornada",
        "o_que_e": "Como são os dias e horários de trabalho da pessoa.",
        "como_preencher": "Escolha o tipo e descreva os dias e horários (entrada, saída e intervalo). Ex.: seg a sex 8h-17h, 1h de almoço.",
        "por_que": "Vai no contrato do eSocial e é base para hora extra e tempo parcial.",
    },
    "horas_semanais": {
        "titulo": "Horas por semana",
        "o_que_e": "Quantidade de horas de trabalho combinadas por semana.",
        "como_preencher": "Jornada cheia é 44. Até 30 horas é tempo parcial.",
        "por_que": "Define tempo parcial no eSocial e o valor da hora.",
    },
    "insalubridade": {
        "titulo": "Insalubridade",
        "o_que_e": "Adicional para quem trabalha exposto a agentes que fazem mal à saúde (barulho, produto químico...).",
        "como_preencher": "Só com laudo técnico (LTCAT). O grau do laudo dá 10%, 20% ou 40% do salário mínimo.",
        "por_que": "É verba obrigatória; pagar sem laudo ou deixar de pagar gera risco trabalhista.",
    },
    "periculosidade": {
        "titulo": "Periculosidade",
        "o_que_e": "Adicional de 30% do salário para atividades de risco (inflamáveis, eletricidade, vigilância, moto).",
        "como_preencher": "Marque só com laudo que confirme a atividade perigosa.",
        "por_que": "Entra no salário e nos encargos todo mês.",
    },
    "vale_transporte": {
        "titulo": "Vale-transporte",
        "o_que_e": "Passagens para ir e voltar do trabalho, pagas pela empresa.",
        "como_preencher": "Informe o custo do mês. A empresa pode descontar até 6% do salário da pessoa.",
        "por_que": "É obrigatório para quem pede; a parte acima dos 6% é custo da empresa.",
    },
    "raca_cor": {
        "titulo": "Raça/cor",
        "o_que_e": "Como a pessoa se declara (branca, preta, parda, amarela ou indígena).",
        "como_preencher": "Pergunte à pessoa. O eSocial não aceita mais \"Não informado\".",
        "por_que": "É obrigatório no cadastro do eSocial.",
    },
    "grau_instrucao": {
        "titulo": "Grau de instrução",
        "o_que_e": "Até onde a pessoa estudou.",
        "como_preencher": "Escolha o último nível completo (ex.: ensino médio completo).",
        "por_que": "É obrigatório no cadastro do eSocial.",
    },
    "cod_municipio": {
        "titulo": "Código IBGE do município",
        "o_que_e": "Número de 7 dígitos que identifica a cidade.",
        "como_preencher": "Procure a cidade no site do IBGE (ex.: Cuiabá é 5103403).",
        "por_que": "O eSocial só aceita o endereço com esse código.",
    },
    "admissao": {
        "titulo": "Data de admissão",
        "o_que_e": "Primeiro dia de trabalho registrado na carteira.",
        "como_preencher": "O dia em que a pessoa começou de fato, mesmo em experiência.",
        "por_que": "A admissão precisa ir ao eSocial até o dia anterior ao início do trabalho.",
    },
    "esocial_ja_cadastrado": {
        "titulo": "Admissão já enviada",
        "o_que_e": "A admissão desta pessoa já foi aceita no eSocial por outro sistema.",
        "como_preencher": "Marque só para quem já tem S-2200 aceito.",
        "por_que": "Evita mandar a admissão de novo, o que o eSocial recusaria.",
    },
    "alteracao_em": {
        "titulo": "Data da mudança",
        "o_que_e": "A partir de quando vale a mudança de dados ou de contrato.",
        "como_preencher": "O dia em que a mudança começou a valer (ex.: o primeiro dia do salário novo). Em branco, vale hoje.",
        "por_que": "Vai no S-2205 ou no S-2206 do eSocial.",
    },
    "motivo_desligamento": {
        "titulo": "Motivo do desligamento",
        "o_que_e": "Por que o contrato acabou: pedido da pessoa, dispensa, acordo, fim de contrato, justa causa...",
        "como_preencher": "Escolha o que aconteceu de verdade. Justa causa exige prova; fale com o escritório antes.",
        "por_que": "Decide as verbas da rescisão, a multa do FGTS e o seguro-desemprego.",
    },
    "aviso_previo": {
        "titulo": "Aviso prévio",
        "o_que_e": "Tempo entre avisar a saída e o último dia: 30 dias, mais 3 por ano completo de casa, até 90.",
        "como_preencher": "Trabalhado: a pessoa trabalha os dias do aviso. Indenizado: a empresa paga os dias sem trabalho. Dispensado: quem pediu para sair é liberado de cumprir.",
        "por_que": "Muda o valor da rescisão e a data de saída no eSocial.",
    },
    "saldo_fgts": {
        "titulo": "Saldo do FGTS",
        "o_que_e": "Quanto a pessoa tem depositado no FGTS deste emprego.",
        "como_preencher": "Veja no FGTS Digital o saldo para fins rescisórios.",
        "por_que": "A multa de 40% (ou 20% no acordo) é calculada sobre ele.",
    },
    "periodo_aquisitivo": {
        "titulo": "Período aquisitivo",
        "o_que_e": "Os 12 meses trabalhados que dão direito a 30 dias de férias.",
        "como_preencher": "Começa no dia da admissão e renova a cada 12 meses. Em branco, o sistema sugere o mais antigo em aberto.",
        "por_que": "As férias precisam ser dadas nos 12 meses seguintes; depois disso, a empresa paga em dobro.",
    },
    "abono": {
        "titulo": "Vender 10 dias (abono)",
        "o_que_e": "A pessoa pode trocar até 1/3 das férias (10 dias) por dinheiro.",
        "como_preencher": "Só se a própria pessoa pedir. Aí sobram 20 dias de descanso.",
        "por_que": "Muda o recibo de férias; a empresa não pode obrigar.",
    },
    "faltas": {
        "titulo": "Faltas sem justificativa",
        "o_que_e": "Faltas que não foram abonadas (sem atestado ou motivo legal).",
        "como_preencher": "Conte as faltas no período aquisitivo.",
        "por_que": "Mais de 5 faltas diminuem os dias de férias (CLT, art. 130).",
    },
}

# nome do campo do formulário -> termo
CAMPOS = {
    "class_trib": "class_trib", "simples_anexo_iv": "simples_anexo_iv", "cnae": "cnae", "fpas": "fpas",
    "cod_terceiros": "cod_terceiros", "aliq_terceiros": "aliq_terceiros", "aliq_rat": "rat", "fap": "fap",
    "cnpj_sindicato": "sindicato", "inicio_esocial": "inicio_esocial", "ambiente_esocial": "ambiente",
    "transmissor_cnpj": "transmissor", "envio_automatico": "envio_automatico", "esocial_ja_iniciado": "ja_iniciado",
    "categoria": "categoria", "cargo": "cbo", "cbo": "cbo", "tipo_jornada": "jornada", "descricao_jornada": "jornada",
    "horario": "jornada", "horas_semanais": "horas_semanais", "insalubridade": "insalubridade",
    "periculosidade": "periculosidade", "vale_transporte": "vale_transporte", "raca_cor": "raca_cor",
    "grau_instrucao": "grau_instrucao", "cod_municipio": "cod_municipio", "data_admissao": "admissao",
    "data_inicio": "admissao", "esocial_ja_cadastrado": "esocial_ja_cadastrado", "alteracao_em": "alteracao_em",
    "a_partir_de": "alteracao_em", "motivo": "motivo_desligamento", "motivo_desligamento": "motivo_desligamento",
    "quem_pediu": "motivo_desligamento", "tipo_aviso": "aviso_previo", "aviso": "aviso_previo",
    "data_aviso": "aviso_previo", "saldo_fgts": "saldo_fgts", "aquisitivo_inicio": "periodo_aquisitivo",
    "dias_abono": "abono", "vender_10": "abono", "faltas_injustificadas": "faltas",
}


def termo_do_campo(nome: str) -> dict | None:
    chave = CAMPOS.get(nome)
    return TERMOS[chave] if chave else None
