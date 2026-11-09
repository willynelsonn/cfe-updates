"""Cálculo da folha usando os dados do banco: folha mensal, férias e 13º salário."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from pessoal.models import Funcionario

from . import calculo as c
from .models import Competencia, Ferias, Holerite, ItemHolerite, Lancamento, Rubrica, criar_rubricas_padrao
from .tabelas import tabela_atualizada, tabelas_do_ano

PAPEIS_AUTOMATICOS = {
    "salario", "dsr_he", "insalubridade", "periculosidade", "salario_familia", "inss", "irrf", "vale_transporte",
    "ferias", "ferias_terco", "ferias_ant", "ferias_terco_ant", "ferias_adiant", "ferias_abono", "ferias_comp",
    "irrf_ferias", "adiant13", "dec13", "desc_adiant13", "inss13", "irrf13",
}
PAPEIS_VARIAVEIS = {"he50", "he100", "dsr_he", "ad_noturno"}


class ErroCalculo(Exception):
    pass


@dataclass
class _Item:
    rubrica: Rubrica
    referencia: Decimal | None
    valor: Decimal


@dataclass
class Demonstrativo:
    """Holerite ainda em memória."""

    tipo: str
    funcionario: Funcionario
    data_pagamento: date
    dias: int = 30
    ferias: Ferias | None = None
    itens: list[_Item] = field(default_factory=list)
    memoria: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    resumo: dict = field(default_factory=dict)

    def add(self, rubrica: Rubrica, referencia, valor) -> Decimal:
        valor = c.r2(valor)
        if valor > 0:
            ref = c.r2(referencia) if referencia is not None else None
            self.itens.append(_Item(rubrica, ref, valor))
        return valor

    def soma(self, filtro) -> Decimal:
        return sum((i.valor * i.rubrica.sinal() for i in self.itens if filtro(i.rubrica)), c.ZERO)


def rubricas_por_papel(empresa) -> dict[str, Rubrica]:
    criar_rubricas_padrao(empresa)
    return {r.papel: r for r in Rubrica.objects.filter(empresa=empresa, ativa=True).exclude(papel="")}


def media_variaveis(funcionario: Funcionario, inicio: date, fim: date) -> Decimal:
    """Média mensal de horas extras e adicional noturno no período (integram férias e 13º)."""
    hs = Holerite.objects.filter(
        funcionario=funcionario, tipo="folha", competencia__tipo="mensal",
        competencia__ano__gte=inicio.year, competencia__ano__lte=fim.year,
    ).select_related("competencia")
    meses, total = 0, c.ZERO
    for h in hs:
        if not (inicio <= h.competencia.inicio <= fim):
            continue
        meses += 1
        total += h.itens.filter(rubrica__papel__in=PAPEIS_VARIAVEIS).aggregate(t=Sum("valor"))["t"] or c.ZERO
    return c.r2(total / meses) if meses else c.ZERO


def remuneracao_fixa(funcionario: Funcionario, tabela) -> Decimal:
    """Salário + adicionais fixos (periculosidade e insalubridade integram férias e 13º)."""
    valor = funcionario.salario
    if funcionario.periculosidade:
        valor += funcionario.salario * Decimal("0.30")
    if funcionario.insalubridade:
        valor += tabela.salario_minimo * funcionario.insalubridade / 100
    return c.r2(valor)


# ---------------------------------------------------------------------------
# Férias
# ---------------------------------------------------------------------------
def calcular_ferias(ferias: Ferias) -> Ferias:
    """Calcula o recibo de férias e a divisão do gozo por mês.

    INSS: as férias integram o salário de contribuição do mês de GOZO. O recibo já retém o
    INSS estimado de cada mês (diferença entre o INSS do mês com e sem as férias) e a folha
    do mês desconta só o restante — assim o líquido da folha nunca fica negativo.
    IRRF: tributado em separado no pagamento (regime de caixa), com dedução do INSS retido.
    """
    f = ferias.funcionario
    tab = tabelas_do_ano(ferias.inicio.year)
    base = remuneracao_fixa(f, tab)
    media = media_variaveis(f, ferias.aquisitivo_inicio, ferias.aquisitivo_fim)
    mensal = base + media
    diaria = mensal / 30
    valor_ferias = c.r2(diaria * ferias.dias)
    terco = c.r2(valor_ferias / 3)
    abono = c.r2(diaria * ferias.dias_abono * Decimal(4) / 3) if ferias.dias_abono else c.ZERO

    parcelas = []
    acumulado_f = acumulado_t = inss_total = c.ZERO
    partes = c.dividir_por_mes(ferias.inicio, ferias.dias)
    for i, (ano, mes, dias) in enumerate(partes):
        if i == len(partes) - 1:
            vf, vt = valor_ferias - acumulado_f, terco - acumulado_t  # evita diferença de centavos
        else:
            vf, vt = c.r2(diaria * dias), c.r2(diaria * dias / 3)
        acumulado_f += vf
        acumulado_t += vt
        ultimo = c.calendar.monthrange(ano, mes)[1]
        dias_trab = 0 if dias >= ultimo else 30 - dias
        salario_mes = base * dias_trab / 30
        tab_mes = tabelas_do_ano(ano)
        inss = c.calcular_inss(salario_mes + vf + vt, tab_mes).valor - c.calcular_inss(salario_mes, tab_mes).valor
        inss_total += inss
        parcelas.append({"ano": ano, "mes": mes, "dias": dias, "ferias": str(vf), "terco": str(vt),
                         "inss": str(inss)})

    deps = f.dependentes.filter(dependente_irrf=True).count()
    irrf = c.calcular_irrf(valor_ferias + terco, inss_total, deps, tab, aplicar_redutor=tab.redutor_irrf_ferias)

    ferias.remuneracao_base = base
    ferias.media_variaveis = media
    ferias.valor_ferias = valor_ferias
    ferias.valor_terco = terco
    ferias.valor_abono = abono
    ferias.valor_inss = inss_total
    ferias.valor_irrf = irrf.valor
    ferias.liquido = valor_ferias + terco + abono - inss_total - irrf.valor
    ferias.parcelas = parcelas
    ferias.memoria = {
        "remuneracao_mensal": str(mensal), "valor_dia": str(c.r2(diaria)),
        "irrf": {"base": str(irrf.base), "aliquota": str(irrf.aliquota), "imposto": str(irrf.imposto_tabela),
                 "reducao_lei_15270": str(irrf.reducao_lei_15270), "simplificado": irrf.usou_desconto_simplificado},
    }
    ferias.status = "calculada"
    ferias.save()
    return ferias


def _recibo_ferias(ferias: Ferias, competencia: Competencia, rub: dict[str, Rubrica]) -> Demonstrativo:
    """Demonstrativo de férias no mês do pagamento.

    Parcelas de gozo no próprio mês do pagamento: rubricas 1016/1017 e INSS (CP 31) do mês.
    Parcelas de gozo em meses seguintes: adiantamento de férias (natureza 1015, NT S-1.3 04/2025)
    e retenção antecipada do INSS, compensada na folha do mês do gozo (natureza 9221).
    """
    d = Demonstrativo("ferias", ferias.funcionario, ferias.data_pagamento, dias=ferias.dias, ferias=ferias)
    for p in ferias.parcelas:
        valor_f, valor_t, inss = Decimal(p["ferias"]), Decimal(p["terco"]), Decimal(p.get("inss", "0"))
        if (p["ano"], p["mes"]) == (competencia.ano, competencia.mes):
            d.add(rub["ferias"], p["dias"], valor_f)
            d.add(rub["ferias_terco"], p["dias"], valor_t)
            d.add(rub["inss_ferias"], None, inss)
        else:
            d.add(rub["ferias_adiant"], p["dias"], valor_f + valor_t)
            d.add(rub["inss_ferias_ant"], None, inss)
    d.add(rub["ferias_abono"], ferias.dias_abono, ferias.valor_abono)
    d.add(rub["irrf_ferias"], None, ferias.valor_irrf)
    d.memoria = {"ferias": ferias.memoria, "parcelas": ferias.parcelas}
    base_fgts = d.soma(lambda r: r.inc_fgts == "11")
    tab = tabelas_do_ano(competencia.ano)
    d.resumo = {
        "valor_irrf": ferias.valor_irrf,
        "valor_inss": d.soma(lambda r: r.papel == "inss_ferias") * -1,
        "base_fgts": c.r2(base_fgts),
        "valor_fgts": c.fgts(base_fgts, tab, ferias.funcionario.aprendiz),
    }
    return d


# ---------------------------------------------------------------------------
# Folha mensal
# ---------------------------------------------------------------------------
def _folha_mensal(
    funcionario: Funcionario,
    competencia: Competencia,
    lancamentos: list[Lancamento],
    rub: dict[str, Rubrica],
    ferias_do_mes: list[Ferias],
    base_inss_outros: Decimal,
    inss_ja_retido: Decimal = Decimal("0"),
) -> Demonstrativo | None:
    ano, mes = competencia.ano, competencia.mes
    tab = tabelas_do_ano(ano)
    dias = c.dias_trabalhados(ano, mes, funcionario.data_admissao, funcionario.data_desligamento)
    if dias == 0:
        return None
    dias_ferias = sum(fe.dias_no_mes(ano, mes) for fe in ferias_do_mes)
    if dias_ferias:
        # Mês comercial: se as férias cobrem o mês inteiro não há salário a pagar.
        ultimo = competencia.fim.day
        dias = max(0, dias - (30 if dias_ferias >= ultimo else dias_ferias))

    d = Demonstrativo("folha", funcionario, competencia.data_pagamento, dias=dias)
    salario = funcionario.salario
    salario_mes = d.add(rub["salario"], dias, salario * dias / 30)
    if funcionario.periculosidade:
        d.add(rub["periculosidade"], 30, salario_mes * Decimal("0.30"))
    if funcionario.insalubridade:
        d.add(rub["insalubridade"], funcionario.insalubridade,
              tab.salario_minimo * funcionario.insalubridade / 100 * dias / 30)

    divisor = c.divisor_horas(funcionario.horas_semanais)
    valor_hora = (salario + (salario * Decimal("0.30") if funcionario.periculosidade else 0)) / divisor
    d.memoria["divisor_horas"] = str(divisor)
    d.memoria["valor_hora"] = str(c.r2(valor_hora))

    total_variaveis_dsr = c.ZERO
    for lanc in lancamentos:
        r = lanc.rubrica
        qtd = lanc.quantidade or c.ZERO
        if r.papel in PAPEIS_AUTOMATICOS:
            d.avisos.append(f"Lançamento de '{r}' ignorado: essa rubrica é calculada automaticamente.")
            continue
        if r.papel == "he50":
            total_variaveis_dsr += d.add(r, qtd, valor_hora * Decimal("1.5") * qtd)
        elif r.papel == "he100":
            total_variaveis_dsr += d.add(r, qtd, valor_hora * 2 * qtd)
        elif r.papel == "ad_noturno":
            total_variaveis_dsr += d.add(r, qtd, valor_hora * Decimal("0.2") * qtd)
        elif r.papel in ("faltas", "dsr_faltas"):
            d.add(r, qtd, salario / 30 * qtd)
        elif lanc.valor is None:
            d.avisos.append(f"Lançamento de '{r}' sem valor foi ignorado.")
        else:
            d.add(r, lanc.quantidade, lanc.valor)

    if total_variaveis_dsr > 0:
        uteis, dsr = c.dias_uteis_e_dsr(ano, mes, competencia.feriados)
        d.add(rub["dsr_he"], dsr, total_variaveis_dsr / uteis * dsr)
        d.memoria["dsr"] = {"dias_uteis": uteis, "dias_repouso": dsr}

    # Férias gozadas neste mês que foram pagas em mês anterior (NT S-1.3 04/2025):
    # informa-se 1016/1017 na competência do gozo e compensa-se o valor adiantado (9221).
    for fe in ferias_do_mes:
        if (fe.data_pagamento.year, fe.data_pagamento.month) == (ano, mes):
            continue
        for p in fe.parcelas:
            if (p["ano"], p["mes"]) == (ano, mes):
                vf, vt = Decimal(p["ferias"]), Decimal(p["terco"])
                d.add(rub["ferias_ant"], p["dias"], vf)
                d.add(rub["ferias_terco_ant"], p["dias"], vt)
                # Compensa o que já foi pago no recibo (bruto menos a retenção antecipada do INSS).
                d.add(rub["ferias_comp"], p["dias"], vf + vt - Decimal(p.get("inss", "0")))

    # INSS: base do mês = este demonstrativo + férias pagas no mês (base_inss_outros).
    # Desconta-se aqui o total do mês menos o INSS já retido no recibo de férias do mês.
    base_inss = d.soma(lambda r: r.inc_cp == "11") + base_inss_outros
    inss = c.calcular_inss(base_inss, tab)
    d.add(rub["inss"], inss.aliquota_efetiva, max(inss.valor - inss_ja_retido, c.ZERO))
    d.memoria["inss"] = {
        "base": str(inss.base), "faixas": [[str(b), str(a), str(v)] for b, a, v in inss.faixas],
        "valor": str(inss.valor), "inclui_ferias": str(base_inss_outros), "retido_nas_ferias": str(inss_ja_retido),
    }

    rend_irrf = d.soma(lambda r: r.inc_irrf == "11")
    deps_irrf = funcionario.dependentes.filter(dependente_irrf=True).count()
    irrf = c.calcular_irrf(rend_irrf, inss.valor, deps_irrf, tab)
    d.add(rub["irrf"], irrf.aliquota, irrf.valor)
    d.memoria["irrf"] = {
        "rendimento_tributavel": str(irrf.rendimento_tributavel), "dependentes": deps_irrf,
        "desconto_simplificado": irrf.usou_desconto_simplificado, "base": str(irrf.base),
        "aliquota": str(irrf.aliquota), "imposto_tabela": str(irrf.imposto_tabela),
        "reducao_lei_15270": str(irrf.reducao_lei_15270), "valor": str(irrf.valor),
    }

    cotas = sum(1 for dep in funcionario.dependentes.all() if dep.da_direito_salario_familia(competencia.inicio))
    dias_vinculo = c.dias_trabalhados(ano, mes, funcionario.data_admissao, funcionario.data_desligamento)
    sf = c.salario_familia(base_inss, cotas, tab, dias_vinculo)
    d.add(rub["salario_familia"], cotas, sf)

    if funcionario.vale_transporte > 0 and salario_mes > 0:
        d.add(rub["vale_transporte"], 6, min(salario_mes * Decimal("0.06"), funcionario.vale_transporte))

    base_fgts = d.soma(lambda r: r.inc_fgts == "11")
    d.resumo = {
        "base_inss": inss.base, "valor_inss": inss.valor,
        "base_irrf": irrf.base, "valor_irrf": irrf.valor, "reducao_irrf": irrf.reducao_lei_15270,
        "dependentes_irrf": deps_irrf, "base_fgts": c.r2(base_fgts),
        "valor_fgts": c.fgts(base_fgts, tab, funcionario.aprendiz), "salario_familia": sf,
    }
    if not tabela_atualizada(ano):
        d.avisos.append(f"Tabelas legais de {ano} não cadastradas: usadas as de {tab.ano}.")
    return d


def _adiantamento_13(funcionario: Funcionario, competencia: Competencia, rub) -> Demonstrativo | None:
    """1ª parcela: metade da remuneração proporcional aos avos até o mês (Lei 4.749, art. 2º). Sem INSS/IRRF."""
    tab = tabelas_do_ano(competencia.ano)
    if Holerite.objects.filter(funcionario=funcionario, tipo="adiant13", competencia__ano=competencia.ano).exclude(
        competencia=competencia
    ).exists():
        return None  # já recebeu (ex.: junto com as férias)
    avos = c.avos_13(competencia.ano, funcionario.data_admissao, funcionario.data_desligamento, competencia.mes)
    if avos == 0:
        return None
    mensal = remuneracao_fixa(funcionario, tab) + media_variaveis(
        funcionario, date(competencia.ano, 1, 1), competencia.fim
    )
    valor = c.r2(mensal * avos / 12 / 2)
    d = Demonstrativo("adiant13", funcionario, competencia.data_adiantamento_13)
    d.add(rub["adiant13"], avos, valor)
    d.resumo = {"base_fgts": valor, "valor_fgts": c.fgts(valor, tab, funcionario.aprendiz)}
    d.memoria = {"avos": avos, "remuneracao": str(mensal)}
    return d


def _decimo_terceiro(funcionario: Funcionario, competencia: Competencia, rub) -> Demonstrativo | None:
    """2ª parcela (até 20/12): 13º integral com INSS e IRRF exclusivos, menos o adiantamento."""
    ano = competencia.ano
    tab = tabelas_do_ano(ano)
    avos = c.avos_13(ano, funcionario.data_admissao, funcionario.data_desligamento)
    if avos == 0:
        return None
    media = media_variaveis(funcionario, date(ano, 1, 1), date(ano, 11, 30))
    mensal = remuneracao_fixa(funcionario, tab) + media
    total = c.r2(mensal * avos / 12)
    adiantado = (
        ItemHolerite.objects.filter(
            holerite__funcionario=funcionario, holerite__tipo="adiant13", holerite__competencia__ano=ano
        ).aggregate(t=Sum("valor"))["t"]
        or c.ZERO
    )
    d = Demonstrativo("dec13", funcionario, competencia.data_pagamento, dias=avos)
    d.add(rub["dec13"], avos, total)
    d.add(rub["desc_adiant13"], None, adiantado)
    inss = c.calcular_inss(total, tab)
    d.add(rub["inss13"], inss.aliquota_efetiva, inss.valor)
    deps = funcionario.dependentes.filter(dependente_irrf=True).count()
    irrf = c.irrf_13(total, inss.valor, deps, tab)
    d.add(rub["irrf13"], irrf.aliquota, irrf.valor)
    base_fgts = total - adiantado
    d.memoria = {
        "avos": avos, "remuneracao": str(mensal), "media_variaveis": str(media), "adiantado": str(adiantado),
        "inss": {"base": str(inss.base), "faixas": [[str(b), str(a), str(v)] for b, a, v in inss.faixas],
                 "valor": str(inss.valor)},
        "irrf": {"base": str(irrf.base), "aliquota": str(irrf.aliquota), "imposto_tabela": str(irrf.imposto_tabela),
                 "reducao_lei_15270": str(irrf.reducao_lei_15270), "valor": str(irrf.valor), "dependentes": deps},
    }
    d.resumo = {
        "base_inss": inss.base, "valor_inss": inss.valor, "base_irrf": irrf.base, "valor_irrf": irrf.valor,
        "reducao_irrf": irrf.reducao_lei_15270, "dependentes_irrf": deps, "base_fgts": c.r2(base_fgts),
        "valor_fgts": c.fgts(base_fgts, tab, funcionario.aprendiz),
    }
    return d


def _gravar(competencia: Competencia, d: Demonstrativo) -> Holerite:
    proventos = sum((i.valor for i in d.itens if i.rubrica.tipo == 1), c.ZERO)
    descontos = sum((i.valor for i in d.itens if i.rubrica.tipo == 2), c.ZERO)
    d.memoria["avisos"] = d.avisos
    hol = Holerite.objects.create(
        competencia=competencia, funcionario=d.funcionario, tipo=d.tipo, ferias=d.ferias,
        data_pagamento=d.data_pagamento, dias_trabalhados=d.dias, salario_contratual=d.funcionario.salario,
        total_proventos=proventos, total_descontos=descontos, liquido=proventos - descontos,
        memoria=d.memoria, **d.resumo,
    )
    ItemHolerite.objects.bulk_create(
        [ItemHolerite(holerite=hol, rubrica=i.rubrica, referencia=i.referencia, valor=i.valor) for i in d.itens]
    )
    return hol


def ferias_que_tocam(funcionario_ids, competencia: Competencia):
    """Férias calculadas com gozo ou pagamento dentro do mês da competência."""
    qs = Ferias.objects.filter(funcionario_id__in=funcionario_ids, status="calculada")
    return [
        fe for fe in qs
        if fe.dias_no_mes(competencia.ano, competencia.mes)
        or (fe.data_pagamento.year, fe.data_pagamento.month) == (competencia.ano, competencia.mes)
    ]


@transaction.atomic
def calcular_competencia(competencia: Competencia) -> list[str]:
    if not competencia.editavel:
        raise ErroCalculo("Competência fechada não pode ser recalculada.")
    empresa = competencia.empresa
    rub = rubricas_por_papel(empresa)
    faltando = {p for p, _ in Rubrica.PAPEL if p} - set(rub) - {"he50", "he100", "ad_noturno", "faltas", "dsr_faltas"}
    if faltando:
        raise ErroCalculo(f"Rubricas obrigatórias inativas ou ausentes: {', '.join(sorted(faltando))}.")

    competencia.holerites.all().delete()
    avisos: list[str] = []
    funcionarios = [
        f for f in Funcionario.objects.filter(empresa=empresa).prefetch_related("dependentes")
        if f.ativo_na_competencia(competencia.ano, competencia.mes)
    ]

    if competencia.decimo_terceiro:
        for func in funcionarios:
            if d := _decimo_terceiro(func, competencia, rub):
                _gravar(competencia, d)
                avisos += [f"{func.nome}: {a}" for a in d.avisos]
    else:
        lancs_por_func: dict[int, list[Lancamento]] = {}
        for lanc in competencia.lancamentos.select_related("rubrica"):
            lancs_por_func.setdefault(lanc.funcionario_id, []).append(lanc)
        ferias = ferias_que_tocam([f.pk for f in funcionarios], competencia)
        for func in funcionarios:
            minhas = [fe for fe in ferias if fe.funcionario_id == func.pk]
            base_inss_ferias = inss_retido = c.ZERO
            for fe in minhas:
                if (fe.data_pagamento.year, fe.data_pagamento.month) == (competencia.ano, competencia.mes):
                    recibo = _recibo_ferias(fe, competencia, rub)
                    base_inss_ferias += recibo.soma(lambda r: r.inc_cp == "11")
                    inss_retido += -recibo.soma(lambda r: r.papel == "inss_ferias")
                    _gravar(competencia, recibo)
            gozo_no_mes = [fe for fe in minhas if fe.dias_no_mes(competencia.ano, competencia.mes)]
            d = _folha_mensal(func, competencia, lancs_por_func.get(func.pk, []), rub, gozo_no_mes,
                              base_inss_ferias, inss_retido)
            if d is not None:
                hol = _gravar(competencia, d)
                if hol.liquido < 0:
                    avisos.append(f"{func.nome}: líquido negativo.")
                avisos += [f"{func.nome}: {a}" for a in d.avisos]
            if competencia.data_adiantamento_13 and (ad := _adiantamento_13(func, competencia, rub)):
                _gravar(competencia, ad)

    competencia.status = "calculada"
    competencia.calculada_em = timezone.now()
    competencia.save(update_fields=["status", "calculada_em"])
    return avisos


# ---------------------------------------------------------------------------
# Resumo de encargos (prévia DCTFWeb / FGTS)
# ---------------------------------------------------------------------------
@dataclass
class ResumoEncargos:
    funcionarios: int
    total_proventos: Decimal
    total_descontos: Decimal
    total_liquido: Decimal
    base_inss: Decimal
    inss_segurados: Decimal
    cpp_patronal: Decimal
    rat: Decimal
    terceiros: Decimal
    salario_familia: Decimal
    irrf: Decimal
    base_fgts: Decimal
    fgts: Decimal

    @property
    def previdencia_a_recolher(self) -> Decimal:
        """Estimativa previdenciária da DCTFWeb: segurados + patronal + RAT + terceiros - salário-família."""
        return self.inss_segurados + self.cpp_patronal + self.rat + self.terceiros - self.salario_familia

    @property
    def darf_estimado(self) -> Decimal:
        return self.previdencia_a_recolher + self.irrf

    @property
    def custo_total_empresa(self) -> Decimal:
        return self.total_proventos + self.cpp_patronal + self.rat + self.terceiros + self.fgts


def resumo_encargos(competencia: Competencia) -> ResumoEncargos:
    empresa = competencia.empresa
    hs = list(competencia.holerites.all())
    soma = lambda attr: sum((getattr(h, attr) for h in hs), c.ZERO)  # noqa: E731
    base_inss = soma("base_inss")
    tab = tabelas_do_ano(competencia.ano)
    cpp = c.r2(base_inss * tab.cpp_patronal / 100) if empresa.recolhe_cpp_patronal else c.ZERO
    rat = c.r2(base_inss * empresa.aliq_rat_ajustada / 100) if empresa.recolhe_cpp_patronal else c.ZERO
    terceiros = c.ZERO if empresa.optante_simples else c.r2(base_inss * empresa.aliq_terceiros / 100)
    return ResumoEncargos(
        funcionarios=len({h.funcionario_id for h in hs}),
        total_proventos=soma("total_proventos"),
        total_descontos=soma("total_descontos"),
        total_liquido=soma("liquido"),
        base_inss=base_inss,
        inss_segurados=soma("valor_inss"),
        cpp_patronal=cpp,
        rat=rat,
        terceiros=terceiros,
        salario_familia=soma("salario_familia"),
        irrf=soma("valor_irrf"),
        base_fgts=soma("base_fgts"),
        fgts=soma("valor_fgts"),
    )
