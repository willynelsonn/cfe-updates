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


# ---------------------------------------------------------------------------
# 13º salário (Leis 4.090/1962 e 4.749/1965)
# ---------------------------------------------------------------------------
def avos_13(ano: int, admissao: date, desligamento: date | None = None, ate_mes: int = 12) -> int:
    """Avos de 13º: 1/12 por mês do ano com 15 ou mais dias de trabalho (Lei 4.090, art. 1º, §2º)."""
    avos = 0
    for mes in range(1, ate_mes + 1):
        ultimo = calendar.monthrange(ano, mes)[1]
        ini = max(date(ano, mes, 1), admissao)
        fim = min(date(ano, mes, ultimo), desligamento) if desligamento else date(ano, mes, ultimo)
        if fim >= ini and (fim - ini).days + 1 >= 15:
            avos += 1
    return avos


def irrf_13(valor_13: Decimal, inss_13: Decimal, dependentes: int, tabela: TabelasAno) -> ResultadoIRRF:
    """IRRF do 13º: tributação exclusiva, só com deduções legais (sem desconto simplificado).

    A redução da Lei 15.270/2025 é aplicada sobre o 13º bruto (art. 3º-A, §3º, da Lei 9.250/1995,
    na redação da Lei 15.270) quando ``tabela.redutor_irrf_13`` estiver ligado.
    """
    rend = r2(valor_13)
    ded_dep = r2(tabela.deducao_dependente_irrf * dependentes)
    base = r2(max(rend - r2(inss_13) - ded_dep, ZERO))
    aliquota, imposto = ZERO, ZERO
    for faixa in tabela.irrf:
        if faixa.ate is None or base <= faixa.ate:
            aliquota = faixa.aliquota
            imposto = max(r2(base * faixa.aliquota / CEM - faixa.deducao), ZERO)
            break
    reducao = ZERO
    red = tabela.redutor_irrf
    if red and tabela.redutor_irrf_13 and imposto > 0:
        if rend <= red.limite_isencao:
            reducao = min(red.reducao_maxima, imposto)
        elif rend <= red.limite_parcial:
            reducao = min(max(r2(red.constante - red.fator * rend), ZERO), imposto)
    valor = r2(imposto - reducao)
    if valor <= tabela.irrf_minimo_retencao:
        valor = ZERO
    return ResultadoIRRF(
        rendimento_tributavel=rend, deducao_inss=r2(inss_13), deducao_dependentes=ded_dep, deducao_pensao=ZERO,
        usou_desconto_simplificado=False, base=base, aliquota=aliquota, imposto_tabela=imposto,
        reducao_lei_15270=reducao, valor=valor,
    )


# ---------------------------------------------------------------------------
# Férias (CLT arts. 129 a 145)
# ---------------------------------------------------------------------------
def dias_direito_ferias(faltas_injustificadas: int) -> int:
    """CLT art. 130."""
    if faltas_injustificadas <= 5:
        return 30
    if faltas_injustificadas <= 14:
        return 24
    if faltas_injustificadas <= 23:
        return 18
    if faltas_injustificadas <= 32:
        return 12
    return 0


def dividir_por_mes(inicio: date, dias: int) -> list[tuple[int, int, int]]:
    """Divide um período de gozo em (ano, mes, dias) por mês civil."""
    partes: list[tuple[int, int, int]] = []
    atual = inicio
    restantes = dias
    while restantes > 0:
        ultimo = calendar.monthrange(atual.year, atual.month)[1]
        no_mes = min(restantes, ultimo - atual.day + 1)
        partes.append((atual.year, atual.month, no_mes))
        restantes -= no_mes
        atual = date(atual.year + (atual.month == 12), atual.month % 12 + 1, 1)
    return partes


# ---------------------------------------------------------------------------
# Prazos
# ---------------------------------------------------------------------------
def proximo_dia_util(d: date, sabado_util: bool = False) -> date:
    """Primeiro dia útil a partir de ``d`` (não considera feriados)."""
    while d.weekday() == 6 or (d.weekday() == 5 and not sabado_util):
        d = date.fromordinal(d.toordinal() + 1)
    return d


def dia_util_anterior(d: date) -> date:
    """Antecipa para o dia útil anterior (sábado/domingo; não considera feriados)."""
    while d.weekday() >= 5:
        d = date.fromordinal(d.toordinal() - 1)
    return d


def quinto_dia_util(ano: int, mes: int) -> date:
    """5º dia útil do mês (CLT art. 459, §1º; sábado conta como dia útil, domingo não)."""
    d, contados = date(ano, mes, 1), 0
    while True:
        if d.weekday() != 6:
            contados += 1
            if contados == 5:
                return d
        d = date.fromordinal(d.toordinal() + 1)


def vencimento_dia_20(ano: int, mes: int) -> date:
    """DCTFWeb e FGTS Digital vencem no dia 20 do mês seguinte, antecipando se não for dia útil."""
    ano_v, mes_v = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return dia_util_anterior(date(ano_v, mes_v, 20))
