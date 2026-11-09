"""Quanto cada funcionário custa para a empresa por mês.

Método (custo mensal "cheio", regime de competência):
  remuneração fixa (salário + adicionais)
+ encargos patronais sobre a remuneração (CPP 20%, RAT x FAP, terceiros — conforme a tributação)
+ FGTS (8%; 2% para aprendiz)
+ provisão de 13º (1/12) e de férias com 1/3 (1/12 x 4/3)
+ encargos e FGTS sobre essas provisões
+ benefícios (vale-transporte pago pela empresa e outros benefícios cadastrados)
+ provisão da multa do FGTS (40% do FGTS do mês), para o caso de dispensa sem justa causa
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.utils import timezone

from . import calculo as c
from .tabelas import tabelas_do_ano

ZERO = Decimal("0")


@dataclass
class Linha:
    grupo: str  # remuneracao | encargos | fgts | provisoes | beneficios
    descricao: str
    valor: Decimal
    explicacao: str = ""


@dataclass
class Custo:
    linhas: list[Linha] = field(default_factory=list)
    remuneracao: Decimal = ZERO

    def add(self, grupo, descricao, valor, explicacao=""):
        valor = c.r2(valor)
        if valor:
            self.linhas.append(Linha(grupo, descricao, valor, explicacao))

    def total_grupo(self, grupo) -> Decimal:
        return sum((l.valor for l in self.linhas if l.grupo == grupo), ZERO)

    @property
    def encargos_fgts(self) -> Decimal:
        return self.total_grupo("encargos") + self.total_grupo("fgts")

    @property
    def provisoes(self) -> Decimal:
        return self.total_grupo("provisoes")

    @property
    def beneficios(self) -> Decimal:
        return self.total_grupo("beneficios")

    @property
    def total(self) -> Decimal:
        return sum((l.valor for l in self.linhas), ZERO)

    @property
    def anual(self) -> Decimal:
        return self.total * 12

    @property
    def multiplicador(self) -> Decimal:
        """Quantas vezes o salário custa (ex.: 1,72 = cada R$ 1 de salário custa R$ 1,72)."""
        return (self.total / self.remuneracao).quantize(Decimal("0.01")) if self.remuneracao else ZERO

    @property
    def grupos(self) -> list[tuple[str, str, Decimal]]:
        nomes = [("remuneracao", "Salário e adicionais"), ("encargos", "Encargos (INSS patronal, RAT, terceiros)"),
                 ("fgts", "FGTS"), ("provisoes", "Provisões (13º, férias, multa FGTS)"),
                 ("beneficios", "Benefícios")]
        return [(k, n, self.total_grupo(k)) for k, n in nomes if self.total_grupo(k)]


def aliquota_encargos(empresa) -> tuple[Decimal, list[tuple[str, Decimal]]]:
    """Alíquota patronal total (%) e o detalhamento."""
    tab = tabelas_do_ano(timezone.localdate().year)
    partes = []
    if empresa.recolhe_cpp_patronal:
        partes.append(("INSS patronal (CPP)", tab.cpp_patronal))
        partes.append((f"RAT {empresa.aliq_rat}% x FAP {empresa.fap:.4f}", empresa.aliq_rat_ajustada))
    if not empresa.optante_simples:
        partes.append((f"Terceiros (Sistema S, salário-educação, Incra) - FPAS {empresa.fpas}",
                       empresa.aliq_terceiros))
    return sum((p for _, p in partes), ZERO), partes


def custo_mensal(empresa, salario: Decimal, *, periculosidade=False, insalubridade=0, vale_transporte=ZERO,
                 beneficios=ZERO, aprendiz=False, ano: int | None = None) -> Custo:
    tab = tabelas_do_ano(ano or timezone.localdate().year)
    salario = Decimal(salario)
    rem = salario
    custo = Custo()
    custo.add("remuneracao", "Salário", salario)
    if periculosidade:
        custo.add("remuneracao", "Adicional de periculosidade (30%)", salario * Decimal("0.30"))
        rem += salario * Decimal("0.30")
    if insalubridade:
        valor = tab.salario_minimo * Decimal(insalubridade) / 100
        custo.add("remuneracao", f"Adicional de insalubridade ({insalubridade}% do mínimo)", valor)
        rem += valor
    custo.remuneracao = c.r2(rem)

    aliq, partes = aliquota_encargos(empresa)
    for nome, pct in partes:
        custo.add("encargos", nome, rem * pct / 100, f"{pct:.2f}% sobre a remuneração")
    aliq_fgts = tab.fgts_aliquota_aprendiz if aprendiz else tab.fgts_aliquota
    custo.add("fgts", f"FGTS ({aliq_fgts}%)", rem * aliq_fgts / 100, "Depositado todo mês pela guia do FGTS Digital")

    prov13 = rem / 12
    provferias = rem / 12 * Decimal(4) / 3
    custo.add("provisoes", "Provisão de 13º salário (1/12)", prov13, "Reserva mensal para pagar o 13º em dezembro")
    custo.add("provisoes", "Provisão de férias + 1/3 (1/12 x 4/3)", provferias, "Reserva mensal para as férias")
    sobre_prov = (prov13 + provferias) * (aliq + aliq_fgts) / 100
    custo.add("provisoes", "Encargos e FGTS sobre as provisões", sobre_prov,
              f"{(aliq + aliq_fgts):.2f}% sobre 13º e férias")
    fgts_total = (rem + prov13 + provferias) * aliq_fgts / 100
    custo.add("provisoes", "Provisão da multa de 40% do FGTS", fgts_total * Decimal("0.40"),
              "Só é paga em dispensa sem justa causa; conservador manter a reserva")

    if vale_transporte:
        vt_empresa = max(Decimal(vale_transporte) - salario * Decimal("0.06"), ZERO)
        custo.add("beneficios", "Vale-transporte (parte da empresa)", vt_empresa,
                  "Custo do VT menos o desconto de até 6% do salário")
    custo.add("beneficios", "Outros benefícios", beneficios, "Plano de saúde, refeição/alimentação etc.")
    return custo


def custo_funcionario(funcionario, ano: int | None = None) -> Custo:
    return custo_mensal(
        funcionario.empresa, funcionario.salario, periculosidade=funcionario.periculosidade,
        insalubridade=funcionario.insalubridade, vale_transporte=funcionario.vale_transporte,
        beneficios=funcionario.beneficios_mensais, aprendiz=funcionario.aprendiz, ano=ano,
    )


def custos_da_empresa(empresa) -> list[tuple]:
    """[(funcionario, Custo)] dos ativos, do maior para o menor custo."""
    hoje = timezone.localdate()
    ativos = empresa.funcionarios.filter(data_desligamento__isnull=True).select_related("cargo")
    lista = [(f, custo_funcionario(f, hoje.year)) for f in ativos]
    return sorted(lista, key=lambda x: x[1].total, reverse=True)
