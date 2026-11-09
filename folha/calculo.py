"""Motor de cálculo da folha (funções puras, sem banco de dados).

Tudo em ``Decimal`` com arredondamento comercial (ROUND_HALF_UP) em centavos.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .tabelas import TabelasAno

ZERO = Decimal("0")
CEM = Decimal("100")


def r2(valor) -> Decimal:
    return Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# INSS do segurado (tabela progressiva)
# ---------------------------------------------------------------------------
@dataclass
class ResultadoINSS:
    base: Decimal
    valor: Decimal
    faixas: list[tuple[Decimal, Decimal, Decimal]] = field(default_factory=list)  # (base faixa, aliq, valor)

    @property
    def aliquota_efetiva(self) -> Decimal:
        return r2(self.valor / self.base * CEM) if self.base else ZERO


def calcular_inss(base: Decimal, tabela: TabelasAno) -> ResultadoINSS:
    base = r2(max(base, ZERO))
    limitada = min(base, tabela.teto_inss)
    anterior = ZERO
    total = ZERO
    faixas = []
    for faixa in tabela.inss:
        if limitada <= anterior:
            break
        parcela = min(limitada, faixa.ate) - anterior
        valor = parcela * faixa.aliquota / CEM
        faixas.append((r2(parcela), faixa.aliquota, r2(valor)))
        total += valor
        anterior = faixa.ate
    return ResultadoINSS(base=base, valor=r2(total), faixas=faixas)


# ---------------------------------------------------------------------------
# IRRF
# ---------------------------------------------------------------------------
@dataclass
class ResultadoIRRF:
    rendimento_tributavel: Decimal
    deducao_inss: Decimal
    deducao_dependentes: Decimal
    deducao_pensao: Decimal
    usou_desconto_simplificado: bool
    base: Decimal
    aliquota: Decimal
    imposto_tabela: Decimal
    reducao_lei_15270: Decimal
    valor: Decimal


def calcular_irrf(
    rendimento_tributavel: Decimal,
    inss: Decimal,
    dependentes: int,
    tabela: TabelasAno,
    pensao: Decimal = ZERO,
    aplicar_redutor: bool = True,
) -> ResultadoIRRF:
    """IRRF mensal.

    Compara as deduções legais (INSS + dependentes + pensão) com o desconto
    simplificado mensal e usa o que for mais vantajoso ao trabalhador.
    Depois aplica a redução da Lei 15.270/2025 (a partir de 2026), calculada
    sobre o rendimento tributável bruto do mês.
    """
    rend = r2(max(rendimento_tributavel, ZERO))
    ded_dep = r2(tabela.deducao_dependente_irrf * dependentes)
    legais = r2(inss) + ded_dep + r2(pensao)
    simplificado = tabela.desconto_simplificado_irrf
    usa_simplificado = simplificado > legais
    deducao = simplificado if usa_simplificado else legais
    base = r2(max(rend - deducao, ZERO))

    aliquota = ZERO
    imposto = ZERO
    for faixa in tabela.irrf:
        if faixa.ate is None or base <= faixa.ate:
            aliquota = faixa.aliquota
            imposto = r2(base * faixa.aliquota / CEM - faixa.deducao)
            break
    imposto = max(imposto, ZERO)

    reducao = ZERO
    red = tabela.redutor_irrf
    if aplicar_redutor and red and imposto > 0:
        if rend <= red.limite_isencao:
            reducao = min(red.reducao_maxima, imposto)
        elif rend <= red.limite_parcial:
            reducao = min(max(r2(red.constante - red.fator * rend), ZERO), imposto)
    valor = r2(imposto - reducao)
    if valor <= tabela.irrf_minimo_retencao:
        # Lei 9.430/1996, art. 67: dispensada a retenção de valor igual ou inferior a R$ 10,00.
        valor = ZERO

    return ResultadoIRRF(
        rendimento_tributavel=rend,
        deducao_inss=r2(inss) if not usa_simplificado else ZERO,
        deducao_dependentes=ded_dep if not usa_simplificado else ZERO,
        deducao_pensao=r2(pensao) if not usa_simplificado else ZERO,
        usou_desconto_simplificado=usa_simplificado,
        base=base,
        aliquota=aliquota,
        imposto_tabela=imposto,
        reducao_lei_15270=reducao,
        valor=valor,
    )


# ---------------------------------------------------------------------------
# Outros
# ---------------------------------------------------------------------------
def salario_familia(remuneracao: Decimal, cotas: int, tabela: TabelasAno, dias: int = 30) -> Decimal:
    if cotas <= 0 or remuneracao > tabela.salario_familia_limite:
        return ZERO
    valor = tabela.salario_familia_cota * cotas
    if dias < 30:
        valor = valor * dias / 30
    return r2(valor)


def fgts(base: Decimal, tabela: TabelasAno, aprendiz: bool = False) -> Decimal:
    aliq = tabela.fgts_aliquota_aprendiz if aprendiz else tabela.fgts_aliquota
    return r2(max(base, ZERO) * aliq / CEM)


def dias_trabalhados(ano: int, mes: int, admissao: date, desligamento: date | None) -> int:
    """Dias a pagar no mês comercial de 30 dias (admissão/desligamento no mês)."""
    ultimo = calendar.monthrange(ano, mes)[1]
    inicio_mes, fim_mes = date(ano, mes, 1), date(ano, mes, ultimo)
    if admissao > fim_mes or (desligamento and desligamento < inicio_mes):
        return 0
    ini = 1 if admissao < inicio_mes else admissao.day
    fim = 30 if not desligamento or desligamento > fim_mes else desligamento.day
    if fim == ultimo:
        fim = 30  # mês comercial: último dia do mês conta como dia 30
    ini = min(ini, 30)
    return max(0, fim - ini + 1)


def dias_uteis_e_dsr(ano: int, mes: int, feriados: int = 0) -> tuple[int, int]:
    """Dias úteis (segunda a sábado) e dias de repouso (domingos + feriados)."""
    ultimo = calendar.monthrange(ano, mes)[1]
    domingos = sum(1 for d in range(1, ultimo + 1) if date(ano, mes, d).weekday() == 6)
    dsr = domingos + feriados
    return ultimo - dsr, dsr


def divisor_horas(horas_semanais: Decimal) -> Decimal:
    """44h -> 220; 40h -> 200; 36h -> 180 ..."""
    return (Decimal(horas_semanais) * 5).quantize(Decimal("1"))


def aviso_previo_dias(admissao: date, desligamento: date) -> int:
    """Lei 12.506/2011: 30 dias + 3 por ano completo, até 90."""
    anos = desligamento.year - admissao.year - ((desligamento.month, desligamento.day) < (admissao.month, admissao.day))
    return min(30 + 3 * max(anos, 0), 90)
