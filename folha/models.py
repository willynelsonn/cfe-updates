from datetime import date
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
        ("41", "41 - Dedução: previdência oficial mensal"),
        ("42", "42 - Dedução: previdência oficial 13º"),
    ]
    INC_FGTS = [("00", "00 - Não é base"), ("11", "11 - Base mensal"), ("12", "12 - Base 13º salário")]

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
        return "FOLHA"

    @property
    def provento(self):
        return self.tipo == 1

    @property
    def desconto(self):
        return self.tipo == 2

    def sinal(self) -> int:
        return {1: 1, 2: -1}.get(self.tipo, 0)


# Rubricas criadas automaticamente para cada empresa nova.
# (código, descrição, tipo, natRubr, incCP, incIRRF, incFGTS, papel)
RUBRICAS_PADRAO = [
    ("1000", "Salário-base", 1, "1000", "11", "11", "11", "salario"),
    ("1010", "Horas extras 50%", 1, "1003", "11", "11", "11", "he50"),
    ("1011", "Horas extras 100%", 1, "1003", "11", "11", "11", "he100"),
    ("1020", "DSR sobre horas extras", 1, "1002", "11", "11", "11", "dsr_he"),
    ("1030", "Adicional noturno", 1, "1205", "11", "11", "11", "ad_noturno"),
    ("1040", "Adicional de insalubridade", 1, "1202", "11", "11", "11", "insalubridade"),
    ("1041", "Adicional de periculosidade", 1, "1203", "11", "11", "11", "periculosidade"),
    ("1099", "Outros proventos", 1, "1099", "11", "11", "11", ""),
    ("1409", "Salário-família", 1, "1409", "51", "9", "00", "salario_familia"),
    ("9201", "INSS", 2, "9201", "31", "41", "00", "inss"),
    ("9203", "IRRF", 2, "9203", "00", "31", "00", "irrf"),
    ("9207", "Faltas", 2, "9207", "11", "11", "11", "faltas"),
    ("9208", "DSR sobre faltas", 2, "9207", "11", "11", "11", "dsr_faltas"),
    ("9216", "Vale-transporte", 2, "9216", "00", "9", "00", "vale_transporte"),
    ("9200", "Adiantamento salarial", 2, "9200", "00", "9", "00", ""),
]


def criar_rubricas_padrao(empresa: Empresa):
    for codigo, desc, tipo, nat, cp, ir, fg, papel in RUBRICAS_PADRAO:
        Rubrica.objects.get_or_create(
            empresa=empresa,
            codigo=codigo,
            defaults=dict(
                descricao=desc, tipo=tipo, natureza=nat, inc_cp=cp, inc_irrf=ir, inc_fgts=fg, papel=papel
            ),
        )


class Competencia(models.Model):
    STATUS = [("aberta", "Aberta"), ("calculada", "Calculada"), ("fechada", "Fechada")]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="competencias")
    ano = models.PositiveSmallIntegerField()
    mes = models.PositiveSmallIntegerField("mês")
    feriados = models.PositiveSmallIntegerField(
        "feriados em dias úteis", default=0, help_text="Usado no cálculo do DSR sobre horas extras."
    )
    data_pagamento = models.DateField("data de pagamento")
    status = models.CharField(max_length=10, choices=STATUS, default="aberta")
    calculada_em = models.DateTimeField(null=True, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-ano", "-mes"]
        constraints = [models.UniqueConstraint(fields=["empresa", "ano", "mes"], name="competencia_unica")]

    def __str__(self):
        return f"{self.mes:02d}/{self.ano}"

    @property
    def per_apur(self):
        return f"{self.ano}-{self.mes:02d}"

    @property
    def inicio(self):
        return date(self.ano, self.mes, 1)

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


class Holerite(models.Model):
    competencia = models.ForeignKey(Competencia, on_delete=models.CASCADE, related_name="holerites")
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name="holerites")
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
        ordering = ["funcionario__nome"]
        constraints = [models.UniqueConstraint(fields=["competencia", "funcionario"], name="holerite_unico")]

    def __str__(self):
        return f"Holerite {self.competencia} - {self.funcionario}"

    @property
    def ide_dm_dev(self):
        """Identificador do demonstrativo no eSocial (único por trabalhador/período)."""
        return f"FP{self.competencia.ano}{self.competencia.mes:02d}{self.funcionario.matricula}"[:30]


class ItemHolerite(models.Model):
    holerite = models.ForeignKey(Holerite, on_delete=models.CASCADE, related_name="itens")
    rubrica = models.ForeignKey(Rubrica, on_delete=models.PROTECT)
    referencia = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    valor = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["rubrica__tipo", "rubrica__codigo"]
