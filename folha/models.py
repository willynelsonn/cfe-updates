from datetime import date, timedelta
from decimal import Decimal

from django.db import models

from empresas.models import Empresa
from pessoal.models import Funcionario


class Rubrica(models.Model):
    """Rubrica (verba) da folha, espelhada no evento S-1010 do eSocial."""

    TIPO = [(1, "Provento"), (2, "Desconto"), (3, "Informativa"), (4, "Informativa dedutora")]
    PAPEL = [
        ("", "Lançamento livre"),
        ("salario", "Salário-base"),
        ("he50", "Horas extras 50%"),
        ("he100", "Horas extras 100%"),
        ("dsr_he", "DSR sobre horas extras"),
        ("ad_noturno", "Adicional noturno"),
        ("insalubridade", "Adicional de insalubridade"),
        ("periculosidade", "Adicional de periculosidade"),
        ("salario_familia", "Salário-família"),
        ("faltas", "Faltas (dias)"),
        ("dsr_faltas", "DSR sobre faltas"),
        ("inss", "INSS do empregado"),
        ("irrf", "IRRF"),
        ("vale_transporte", "Vale-transporte"),
        # Férias
        ("ferias", "Férias gozadas (pagas no mês)"),
        ("ferias_terco", "1/3 de férias (pago no mês)"),
        ("ferias_ant", "Férias gozadas (pagas em mês anterior)"),
        ("ferias_terco_ant", "1/3 de férias (pago em mês anterior)"),
        ("ferias_adiant", "Adiantamento de férias (gozo em mês seguinte)"),
        ("ferias_abono", "Abono pecuniário de férias (com 1/3)"),
        ("ferias_comp", "Compensação do adiantamento de férias"),
        ("irrf_ferias", "IRRF sobre férias"),
        ("inss_ferias", "INSS sobre férias (gozo no mês do pagamento)"),
        ("inss_ferias_ant", "Retenção antecipada do INSS das férias (gozo em mês seguinte)"),
        # Rescisão
        ("resc_saldo", "Saldo de salário (rescisão)"),
        ("resc_aviso", "Aviso prévio indenizado"),
        ("resc_13", "13º proporcional (rescisão)"),
        ("resc_13_aviso", "13º sobre aviso prévio indenizado"),
        ("resc_ferias_prop", "Férias proporcionais + 1/3 (indenizadas)"),
        ("resc_ferias_venc", "Férias vencidas + 1/3 (indenizadas)"),
        ("resc_479", "Indenização do art. 479 da CLT"),
        ("resc_desc_aviso", "Desconto de aviso prévio / art. 480"),
        # 13º salário
        ("adiant13", "Adiantamento do 13º (1ª parcela)"),
        ("dec13", "13º salário"),
        ("desc_adiant13", "Desconto do adiantamento do 13º"),
        ("inss13", "INSS sobre 13º"),
        ("irrf13", "IRRF sobre 13º"),
    ]
    INC_CP = [
        ("00", "00 - Não é base de cálculo"),
        ("11", "11 - Base mensal"),
        ("12", "12 - Base 13º salário"),
        ("31", "31 - Contribuição descontada do segurado (mensal)"),
        ("32", "32 - Contribuição descontada do segurado (13º)"),
        ("51", "51 - Salário-família"),
    ]
    INC_IRRF = [
        ("0", "0 - Rendimento não tributável"),
        ("9", "9 - Verba de natureza diversa de rendimento (ex.: descontos diversos)"),
        ("11", "11 - Remuneração mensal"),
        ("12", "12 - 13º salário"),
        ("13", "13 - Férias"),
        ("31", "31 - Retenção IRRF mensal"),
        ("32", "32 - Retenção IRRF 13º salário"),
        ("33", "33 - Retenção IRRF férias"),
        ("41", "41 - Dedução: previdência oficial mensal"),
        ("42", "42 - Dedução: previdência oficial 13º"),
        ("73", "73 - Isento: indenização por rescisão"),
        ("74", "74 - Isento: abono pecuniário"),
    ]
    INC_FGTS = [("00", "00 - Não é base"), ("11", "11 - Base mensal"), ("12", "12 - Base 13º salário"),
                ("21", "21 - Base aviso prévio indenizado")]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="rubricas")
    codigo = models.CharField("código", max_length=30)
    descricao = models.CharField("descrição", max_length=100)
    tipo = models.PositiveSmallIntegerField(choices=TIPO)
    natureza = models.CharField("natureza eSocial (natRubr)", max_length=4)
    inc_cp = models.CharField("incidência INSS", max_length=2, choices=INC_CP, default="11")
    inc_irrf = models.CharField("incidência IRRF", max_length=4, choices=INC_IRRF, default="11")
    inc_fgts = models.CharField("incidência FGTS", max_length=2, choices=INC_FGTS, default="11")
    papel = models.CharField(
        "uso no cálculo automático", max_length=20, choices=PAPEL, blank=True,
        help_text="Rubricas com papel são calculadas automaticamente pelo sistema.",
    )
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["codigo"]
        constraints = [models.UniqueConstraint(fields=["empresa", "codigo"], name="rubrica_unica_por_empresa")]

    def __str__(self):
        return f"{self.codigo} - {self.descricao}"

    @property
    def ide_tab_rubr(self):
        # Tabela própria, para não colidir com rubricas de outro sistema (ex.: Domínio) no eSocial.
        return "FOLHAWEB"

    @property
    def provento(self):
        return self.tipo == 1

    @property
    def desconto(self):
        return self.tipo == 2

    def sinal(self) -> int:
        return {1: 1, 2: -1}.get(self.tipo, 0)


# Rubricas criadas automaticamente para cada empresa.
# (código, descrição, tipo, natRubr, incCP, incIRRF, incFGTS, papel)
# Naturezas de férias conforme NT S-1.3 04/2025 (1015/1016/1017/9221, vigentes desde 01/2026).
RUBRICAS_PADRAO = [
    ("1000", "Salário-base", 1, "1000", "11", "11", "11", "salario"),
    ("1010", "Horas extras 50%", 1, "1003", "11", "11", "11", "he50"),
    ("1011", "Horas extras 100%", 1, "1003", "11", "11", "11", "he100"),
    ("1020", "DSR sobre horas extras", 1, "1002", "11", "11", "11", "dsr_he"),
    ("1030", "Adicional noturno", 1, "1205", "11", "11", "11", "ad_noturno"),
    ("1040", "Adicional de insalubridade", 1, "1202", "11", "11", "11", "insalubridade"),
    ("1041", "Adicional de periculosidade", 1, "1203", "11", "11", "11", "periculosidade"),
    ("1099", "Outros proventos", 1, "1099", "11", "11", "11", ""),
    ("1100", "Férias", 1, "1016", "11", "13", "11", "ferias"),
    ("1101", "1/3 constitucional de férias", 1, "1017", "11", "13", "11", "ferias_terco"),
    ("1102", "Férias (pagas no mês anterior)", 1, "1016", "11", "9", "11", "ferias_ant"),
    ("1103", "1/3 de férias (pago no mês anterior)", 1, "1017", "11", "9", "11", "ferias_terco_ant"),
    ("1104", "Adiantamento de férias (com 1/3)", 1, "1015", "00", "13", "00", "ferias_adiant"),
    ("1105", "Abono pecuniário de férias (com 1/3)", 1, "1023", "00", "74", "00", "ferias_abono"),
    ("1409", "Salário-família", 1, "1409", "51", "9", "00", "salario_familia"),
    ("5001", "13º salário", 1, "5001", "12", "12", "12", "dec13"),
    ("5504", "Adiantamento do 13º salário", 1, "5504", "00", "9", "12", "adiant13"),
    ("9201", "INSS", 2, "9201", "31", "41", "00", "inss"),
    ("9202", "INSS sobre 13º salário", 2, "9201", "32", "42", "00", "inss13"),
    ("9203", "IRRF", 2, "9203", "00", "31", "00", "irrf"),
    ("9204", "IRRF sobre férias", 2, "9203", "00", "33", "00", "irrf_ferias"),
    ("9206", "INSS sobre férias", 2, "9201", "31", "41", "00", "inss_ferias"),
    ("9209", "Retenção antecipada do INSS das férias", 2, "9200", "00", "9", "00", "inss_ferias_ant"),
    ("9205", "IRRF sobre 13º salário", 2, "9203", "00", "32", "00", "irrf13"),
    ("9207", "Faltas", 2, "9207", "11", "11", "11", "faltas"),
    ("9208", "DSR sobre faltas", 2, "9207", "11", "11", "11", "dsr_faltas"),
    ("9214", "Desconto do adiantamento do 13º", 2, "9214", "00", "9", "12", "desc_adiant13"),
    ("9216", "Vale-transporte", 2, "9216", "00", "9", "00", "vale_transporte"),
    ("9221", "Compensação do adiantamento de férias", 2, "9221", "00", "9", "00", "ferias_comp"),
    ("9200", "Adiantamento salarial", 2, "9200", "00", "9", "00", ""),
    # Rescisão (S-2299). Naturezas 6000-6003 conferidas na Tabela 03; 6006/6007/6129/9299 a confirmar.
    ("6000", "Saldo de salário", 1, "6000", "11", "11", "11", "resc_saldo"),
    ("6001", "13º salário sobre aviso prévio indenizado", 1, "6001", "12", "12", "12", "resc_13_aviso"),
    ("6002", "13º salário proporcional", 1, "6002", "12", "12", "12", "resc_13"),
    ("6003", "Aviso prévio indenizado", 1, "6003", "00", "73", "21", "resc_aviso"),
    ("6006", "Férias proporcionais + 1/3 (indenizadas)", 1, "6006", "00", "73", "00", "resc_ferias_prop"),
    ("6007", "Férias vencidas + 1/3 (indenizadas)", 1, "6007", "00", "73", "00", "resc_ferias_venc"),
    ("6129", "Indenização do art. 479 da CLT", 1, "6129", "00", "73", "00", "resc_479"),
    ("9299", "Desconto de aviso prévio não cumprido / art. 480", 2, "9299", "00", "9", "00", "resc_desc_aviso"),
]


def criar_rubricas_padrao(empresa: Empresa):
    existentes = set(Rubrica.objects.filter(empresa=empresa).values_list("codigo", flat=True))
    novas = [
        Rubrica(empresa=empresa, codigo=codigo, descricao=desc, tipo=tipo, natureza=nat,
                inc_cp=cp, inc_irrf=ir, inc_fgts=fg, papel=papel)
        for codigo, desc, tipo, nat, cp, ir, fg, papel in RUBRICAS_PADRAO
        if codigo not in existentes
    ]
    if novas:
        Rubrica.objects.bulk_create(novas)


class Competencia(models.Model):
    STATUS = [("aberta", "Aberta"), ("calculada", "Calculada"), ("fechada", "Fechada")]
    TIPO = [("mensal", "Folha mensal"), ("13", "13º salário (2ª parcela)")]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="competencias")
    tipo = models.CharField(max_length=6, choices=TIPO, default="mensal")
    ano = models.PositiveSmallIntegerField()
    mes = models.PositiveSmallIntegerField("mês", help_text="Para o 13º salário use 12.")
    feriados = models.PositiveSmallIntegerField(
        "feriados em dias úteis", default=0, help_text="Usado no cálculo do DSR sobre horas extras."
    )
    data_pagamento = models.DateField(
        "data de pagamento", help_text="Salário: até o 5º dia útil do mês seguinte. 13º: até 20/12."
    )
    data_adiantamento_13 = models.DateField(
        "pagar a 1ª parcela do 13º em", null=True, blank=True,
        help_text="Preencha (até 30/11) para calcular o adiantamento do 13º junto com esta folha.",
    )
    status = models.CharField(max_length=10, choices=STATUS, default="aberta")
    calculada_em = models.DateTimeField(null=True, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-ano", "-mes", "tipo"]
        constraints = [models.UniqueConstraint(fields=["empresa", "tipo", "ano", "mes"], name="competencia_unica")]

    def __str__(self):
        return f"13º/{self.ano}" if self.tipo == "13" else f"{self.mes:02d}/{self.ano}"

    @property
    def decimo_terceiro(self):
        return self.tipo == "13"

    @property
    def per_apur(self):
        """Período de apuração no eSocial: AAAA-MM (mensal) ou AAAA (13º salário)."""
        return str(self.ano) if self.decimo_terceiro else f"{self.ano}-{self.mes:02d}"

    @property
    def ind_apuracao(self):
        return 2 if self.decimo_terceiro else 1

    @property
    def inicio(self):
        return date(self.ano, self.mes, 1)

    @property
    def fim(self):
        proximo = date(self.ano + (self.mes == 12), self.mes % 12 + 1, 1)
        return proximo - timedelta(days=1)

    @property
    def editavel(self):
        return self.status != "fechada"


class Lancamento(models.Model):
    """Evento variável do mês: horas extras, faltas, comissões, descontos..."""

    competencia = models.ForeignKey(Competencia, on_delete=models.CASCADE, related_name="lancamentos")
    funcionario = models.ForeignKey(
        Funcionario, on_delete=models.CASCADE, related_name="lancamentos", verbose_name="funcionário"
    )
    rubrica = models.ForeignKey(Rubrica, on_delete=models.PROTECT)
    quantidade = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Horas (horas extras, adicional noturno) ou dias (faltas).",
    )
    valor = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Valor em R$ (para rubricas sem cálculo automático).",
    )
    observacao = models.CharField("observação", max_length=200, blank=True)

    class Meta:
        ordering = ["funcionario__nome", "rubrica__codigo"]

    def __str__(self):
        return f"{self.funcionario} - {self.rubrica}"


class Ferias(models.Model):
    """Programação e recibo de férias (CLT arts. 129 a 145)."""

    STATUS = [("programada", "Programada"), ("calculada", "Calculada"), ("cancelada", "Cancelada")]

    funcionario = models.ForeignKey(
        Funcionario, on_delete=models.CASCADE, related_name="ferias", verbose_name="funcionário"
    )
    aquisitivo_inicio = models.DateField("início do período aquisitivo")
    aquisitivo_fim = models.DateField("fim do período aquisitivo")
    faltas_injustificadas = models.PositiveSmallIntegerField(
        "faltas injustificadas no período aquisitivo", default=0,
        help_text="Reduzem os dias de direito (CLT art. 130): até 5 → 30 dias; 6-14 → 24; 15-23 → 18; 24-32 → 12.",
    )
    inicio = models.DateField("início do gozo")
    dias = models.PositiveSmallIntegerField("dias de gozo")
    dias_abono = models.PositiveSmallIntegerField(
        "dias vendidos (abono pecuniário)", default=0,
        help_text="Até 1/3 dos dias de direito (CLT art. 143). Deve ser pedido pelo empregado.",
    )
    data_pagamento = models.DateField(
        "data do pagamento", help_text="Até 2 dias antes do início do gozo (CLT art. 145)."
    )
    data_aviso = models.DateField("data do aviso de férias", help_text="Ao menos 30 dias antes (CLT art. 135).")
    status = models.CharField(max_length=12, choices=STATUS, default="programada")

    # Valores calculados
    remuneracao_base = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    media_variaveis = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    valor_ferias = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    valor_terco = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    valor_abono = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    valor_inss = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    valor_irrf = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    liquido = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    parcelas = models.JSONField(
        default=list, blank=True,
        help_text="Divisão do gozo por mês: [{ano, mes, dias, ferias, terco, inss}]",
    )
    memoria = models.JSONField(default=dict, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-inicio"]
        verbose_name = "férias"
        verbose_name_plural = "férias"

    def __str__(self):
        return f"Férias de {self.funcionario.nome} a partir de {self.inicio:%d/%m/%Y}"

    @property
    def fim(self) -> date:
        return self.inicio + timedelta(days=self.dias - 1)

    @property
    def retorno(self) -> date:
        return self.fim + timedelta(days=1)

    def dias_no_mes(self, ano: int, mes: int) -> int:
        for p in self.parcelas:
            if p["ano"] == ano and p["mes"] == mes:
                return p["dias"]
        return 0


class Rescisao(models.Model):
    """Rescisão do contrato de trabalho (TRCT) — CLT arts. 477 a 487."""

    AVISO = [
        ("indenizado", "Aviso prévio indenizado (empresa paga sem trabalhar)"),
        ("trabalhado", "Aviso prévio trabalhado"),
        ("dispensado", "Pedido de demissão com aviso dispensado pela empresa"),
        ("nao_cumprido", "Pedido de demissão sem cumprir o aviso (desconto)"),
        ("nenhum", "Sem aviso prévio (justa causa, término de contrato, falecimento)"),
    ]
    STATUS = [("calculada", "Calculada"), ("enviada", "Enviada ao eSocial"), ("cancelada", "Cancelada")]

    funcionario = models.ForeignKey(
        Funcionario, on_delete=models.CASCADE, related_name="rescisoes", verbose_name="funcionário"
    )
    motivo = models.CharField(max_length=2, choices=Funcionario.MOTIVO_DESLIGAMENTO)
    data_aviso = models.DateField("data do aviso", null=True, blank=True)
    tipo_aviso = models.CharField("aviso prévio", max_length=12, choices=AVISO, default="indenizado")
    data_desligamento = models.DateField(
        "último dia trabalhado", help_text="Com aviso indenizado, é o dia da comunicação da dispensa."
    )
    data_pagamento = models.DateField(
        "data do pagamento", help_text="Até 10 dias corridos após o término do contrato (CLT art. 477, §6º)."
    )
    saldo_fgts = models.DecimalField(
        "saldo do FGTS para fins rescisórios (R$)", max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="Do extrato do FGTS Digital. Usado para estimar a multa de 40% (ou 20% no acordo).",
    )
    faltas_periodo_ferias = models.PositiveSmallIntegerField(
        "faltas injustificadas no período aquisitivo atual", default=0
    )
    status = models.CharField(max_length=10, choices=STATUS, default="calculada")

    dias_aviso = models.PositiveSmallIntegerField(default=0)
    data_projetada = models.DateField("término projetado (com aviso)", null=True, blank=True)
    total_proventos = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total_descontos = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    liquido = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    valor_inss = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    valor_irrf = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    fgts_rescisorio = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    multa_fgts = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    itens = models.JSONField(default=list, blank=True)
    memoria = models.JSONField(default=dict, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_desligamento"]
        verbose_name = "rescisão"
        verbose_name_plural = "rescisões"

    def __str__(self):
        return f"Rescisão de {self.funcionario.nome} em {self.data_desligamento:%d/%m/%Y}"

    @property
    def prazo_pagamento(self) -> date:
        return self.data_desligamento + timedelta(days=10)

    @property
    def per_apur(self):
        return f"{self.data_desligamento.year}-{self.data_desligamento.month:02d}"

    @property
    def ide_dm_dev(self):
        return f"RE{self.data_desligamento:%Y%m}{self.funcionario.matricula}"[:30]

    eh_rescisao = True  # usado na montagem do S-1210 (tpPgto = 2)


class Holerite(models.Model):
    """Demonstrativo de valores (dmDev no eSocial). Um trabalhador pode ter vários no mês."""

    TIPO = [
        ("folha", "Folha mensal"),
        ("ferias", "Recibo de férias"),
        ("adiant13", "1ª parcela do 13º"),
        ("dec13", "13º salário"),
    ]
    PREFIXO = {"folha": "FP", "ferias": "FE", "adiant13": "AD", "dec13": "DT"}

    competencia = models.ForeignKey(Competencia, on_delete=models.CASCADE, related_name="holerites")
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name="holerites")
    tipo = models.CharField(max_length=8, choices=TIPO, default="folha")
    ferias = models.ForeignKey(Ferias, on_delete=models.SET_NULL, null=True, blank=True)
    data_pagamento = models.DateField(null=True)
    dias_trabalhados = models.PositiveSmallIntegerField(default=30)
    salario_contratual = models.DecimalField(max_digits=12, decimal_places=2)
    total_proventos = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total_descontos = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    liquido = models.DecimalField("líquido", max_digits=12, decimal_places=2, default=Decimal("0"))
    base_inss = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    valor_inss = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    base_irrf = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    valor_irrf = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    reducao_irrf = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    dependentes_irrf = models.PositiveSmallIntegerField(default=0)
    base_fgts = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    valor_fgts = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    salario_familia = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    memoria = models.JSONField("memória de cálculo", default=dict)

    class Meta:
        ordering = ["funcionario__nome", "tipo"]
        constraints = [
            models.UniqueConstraint(fields=["competencia", "funcionario", "tipo", "ferias"], name="holerite_unico")
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.competencia} - {self.funcionario}"

    @property
    def ide_dm_dev(self):
        """Identificador do demonstrativo no eSocial (único por trabalhador/período)."""
        comp = self.competencia
        sufixo = f"F{self.ferias_id}" if self.ferias_id else ""
        return f"{self.PREFIXO[self.tipo]}{comp.ano}{comp.mes:02d}{self.funcionario.matricula}{sufixo}"[:30]


class ItemHolerite(models.Model):
    holerite = models.ForeignKey(Holerite, on_delete=models.CASCADE, related_name="itens")
    rubrica = models.ForeignKey(Rubrica, on_delete=models.PROTECT)
    referencia = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    valor = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["rubrica__tipo", "rubrica__codigo"]


class Guia(models.Model):
    """Guias de recolhimento geradas a partir do eSocial."""

    TIPO = [("darf", "DARF DCTFWeb (INSS + IRRF)"), ("fgts", "GFD - FGTS Digital")]
    STATUS = [
        ("prevista", "Prevista (aguardando eSocial)"),
        ("disponivel", "Pronta para emitir"),
        ("emitida", "Emitida"),
        ("paga", "Paga"),
        ("erro", "Erro"),
    ]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="guias")
    competencia = models.ForeignKey(Competencia, on_delete=models.CASCADE, related_name="guias")
    tipo = models.CharField(max_length=4, choices=TIPO)
    valor_estimado = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    vencimento = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS, default="prevista")
    pdf = models.BinaryField(null=True, blank=True, editable=False)
    numero_documento = models.CharField(max_length=60, blank=True)
    mensagem = models.TextField(blank=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["vencimento", "tipo"]
        constraints = [models.UniqueConstraint(fields=["competencia", "tipo"], name="guia_unica")]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.competencia}"
