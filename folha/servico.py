"""Cálculo da folha usando os dados do banco."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from pessoal.models import Funcionario

from . import calculo as c
from .models import Competencia, Holerite, ItemHolerite, Lancamento, Rubrica, criar_rubricas_padrao
from .tabelas import tabela_atualizada, tabelas_do_ano

PAPEIS_AUTOMATICOS = {
    "salario", "dsr_he", "insalubridade", "periculosidade", "salario_familia", "inss", "irrf", "vale_transporte",
}


class ErroCalculo(Exception):
    pass


@dataclass
class _Item:
    rubrica: Rubrica
    referencia: Decimal | None
    valor: Decimal


@dataclass
class ResultadoFuncionario:
    funcionario: Funcionario
    dias: int
    itens: list[_Item] = field(default_factory=list)
    memoria: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)

    def soma(self, filtro) -> Decimal:
        return sum((i.valor * i.rubrica.sinal() for i in self.itens if filtro(i.rubrica)), c.ZERO)


def _rubricas_por_papel(empresa) -> dict[str, Rubrica]:
    criar_rubricas_padrao(empresa)
    return {r.papel: r for r in Rubrica.objects.filter(empresa=empresa, ativa=True).exclude(papel="")}


def calcular_funcionario(
    funcionario: Funcionario,
    competencia: Competencia,
    lancamentos: list[Lancamento],
    rubricas: dict[str, Rubrica],
) -> ResultadoFuncionario | None:
    ano, mes = competencia.ano, competencia.mes
    tab = tabelas_do_ano(ano)
    dias = c.dias_trabalhados(ano, mes, funcionario.data_admissao, funcionario.data_desligamento)
    if dias == 0:
        return None

    res = ResultadoFuncionario(funcionario=funcionario, dias=dias)

    def add(papel_ou_rubrica, referencia, valor):
        rub = rubricas[papel_ou_rubrica] if isinstance(papel_ou_rubrica, str) else papel_ou_rubrica
        valor = c.r2(valor)
        if valor > 0:
            res.itens.append(_Item(rub, c.r2(referencia) if referencia is not None else None, valor))
        return valor

    salario = funcionario.salario
    salario_mes = add("salario", dias, salario * dias / 30)

    periculosidade = c.ZERO
    if funcionario.periculosidade:
        periculosidade = add("periculosidade", 30, salario_mes * Decimal("0.30"))
    if funcionario.insalubridade:
        add("insalubridade", funcionario.insalubridade, tab.salario_minimo * funcionario.insalubridade / 100 * dias / 30)

    divisor = c.divisor_horas(funcionario.horas_semanais)
    # Periculosidade integra o valor da hora para horas extras (Súmula 132 TST).
    valor_hora = (salario + (salario * Decimal("0.30") if funcionario.periculosidade else 0)) / divisor
    res.memoria["divisor_horas"] = str(divisor)
    res.memoria["valor_hora"] = str(c.r2(valor_hora))

    total_variaveis_dsr = c.ZERO
    for lanc in lancamentos:
        rub = lanc.rubrica
        qtd = lanc.quantidade or c.ZERO
        if rub.papel in PAPEIS_AUTOMATICOS:
            res.avisos.append(f"Lançamento de '{rub}' ignorado: essa rubrica é calculada automaticamente.")
            continue
        if rub.papel == "he50":
            total_variaveis_dsr += add(rub, qtd, valor_hora * Decimal("1.5") * qtd)
        elif rub.papel == "he100":
            total_variaveis_dsr += add(rub, qtd, valor_hora * 2 * qtd)
        elif rub.papel == "ad_noturno":
            total_variaveis_dsr += add(rub, qtd, valor_hora * Decimal("0.2") * qtd)
        elif rub.papel in ("faltas", "dsr_faltas"):
            add(rub, qtd, salario / 30 * qtd)
        else:
            if lanc.valor is None:
                res.avisos.append(f"Lançamento de '{rub}' sem valor foi ignorado.")
                continue
            add(rub, lanc.quantidade, lanc.valor)

    if total_variaveis_dsr > 0:
        uteis, dsr = c.dias_uteis_e_dsr(ano, mes, competencia.feriados)
        add("dsr_he", dsr, total_variaveis_dsr / uteis * dsr)
        res.memoria["dsr"] = {"dias_uteis": uteis, "dias_repouso": dsr}

    # INSS
    base_inss = res.soma(lambda r: r.inc_cp == "11")
    inss = c.calcular_inss(base_inss, tab)
    add("inss", inss.aliquota_efetiva, inss.valor)
    res.memoria["inss"] = {
        "base": str(inss.base),
        "faixas": [[str(b), str(a), str(v)] for b, a, v in inss.faixas],
        "valor": str(inss.valor),
    }

    # IRRF
    rend_irrf = res.soma(lambda r: r.inc_irrf == "11")
    deps_irrf = funcionario.dependentes.filter(dependente_irrf=True).count()
    irrf = c.calcular_irrf(rend_irrf, inss.valor, deps_irrf, tab)
    add("irrf", irrf.aliquota, irrf.valor)
    res.memoria["irrf"] = {
        "rendimento_tributavel": str(irrf.rendimento_tributavel),
        "dependentes": deps_irrf,
        "desconto_simplificado": irrf.usou_desconto_simplificado,
        "base": str(irrf.base),
        "aliquota": str(irrf.aliquota),
        "imposto_tabela": str(irrf.imposto_tabela),
        "reducao_lei_15270": str(irrf.reducao_lei_15270),
        "valor": str(irrf.valor),
    }

    # Salário-família
    ref_data = competencia.inicio
    cotas = sum(1 for d in funcionario.dependentes.all() if d.da_direito_salario_familia(ref_data))
    sf = c.salario_familia(base_inss, cotas, tab, dias)
    add("salario_familia", cotas, sf)

    # Vale-transporte (até 6% do salário-base)
    if funcionario.vale_transporte > 0:
        add("vale_transporte", 6, min(salario_mes * Decimal("0.06"), funcionario.vale_transporte))

    base_fgts = res.soma(lambda r: r.inc_fgts == "11")
    res.memoria["fgts"] = {
        "base": str(c.r2(base_fgts)),
        "valor": str(c.fgts(base_fgts, tab, funcionario.aprendiz)),
    }
    res.memoria["_resumo"] = {
        "base_inss": inss.base, "valor_inss": inss.valor,
        "base_irrf": irrf.base, "valor_irrf": irrf.valor, "reducao_irrf": irrf.reducao_lei_15270,
        "dependentes_irrf": deps_irrf,
        "base_fgts": c.r2(base_fgts), "valor_fgts": c.fgts(base_fgts, tab, funcionario.aprendiz),
        "salario_familia": sf,
    }
    if not tabela_atualizada(ano):
        res.avisos.append(f"Tabelas legais de {ano} não cadastradas: usadas as de {tab.ano}.")
    return res


@transaction.atomic
def calcular_competencia(competencia: Competencia) -> list[str]:
    if not competencia.editavel:
        raise ErroCalculo("Competência fechada não pode ser recalculada.")
    empresa = competencia.empresa
    rubricas = _rubricas_por_papel(empresa)
    faltando = {"salario", "inss", "irrf", "salario_familia", "dsr_he"} - set(rubricas)
    if faltando:
        raise ErroCalculo(f"Rubricas obrigatórias ausentes: {', '.join(sorted(faltando))}.")

    competencia.holerites.all().delete()
    avisos: list[str] = []
    lancs_por_func: dict[int, list[Lancamento]] = {}
    for lanc in competencia.lancamentos.select_related("rubrica"):
        lancs_por_func.setdefault(lanc.funcionario_id, []).append(lanc)

    for func in Funcionario.objects.filter(empresa=empresa).prefetch_related("dependentes"):
        if not func.ativo_na_competencia(competencia.ano, competencia.mes):
            continue
        res = calcular_funcionario(func, competencia, lancs_por_func.get(func.pk, []), rubricas)
        if res is None:
            continue
        resumo = res.memoria.pop("_resumo")
        proventos = sum((i.valor for i in res.itens if i.rubrica.tipo == 1), c.ZERO)
        descontos = sum((i.valor for i in res.itens if i.rubrica.tipo == 2), c.ZERO)
        res.memoria["avisos"] = res.avisos
        hol = Holerite.objects.create(
            competencia=competencia,
            funcionario=func,
            dias_trabalhados=res.dias,
            salario_contratual=func.salario,
            total_proventos=proventos,
            total_descontos=descontos,
            liquido=proventos - descontos,
            memoria=res.memoria,
            **resumo,
        )
        ItemHolerite.objects.bulk_create(
            [ItemHolerite(holerite=hol, rubrica=i.rubrica, referencia=i.referencia, valor=i.valor) for i in res.itens]
        )
        if hol.liquido < 0:
            res.avisos.append("Líquido negativo.")
        avisos += [f"{func.nome}: {a}" for a in res.avisos]

    competencia.status = "calculada"
    competencia.calculada_em = timezone.now()
    competencia.save(update_fields=["status", "calculada_em"])
    return avisos


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
        """Valor estimado da DCTFWeb (previdenciário): segurados + patronal + RAT + terceiros - salário-família."""
        return self.inss_segurados + self.cpp_patronal + self.rat + self.terceiros - self.salario_familia

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
        funcionarios=len(hs),
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
