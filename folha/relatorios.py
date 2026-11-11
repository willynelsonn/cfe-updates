"""Relatórios da folha: cada relatório vira uma tabela que pode ser vista, impressa (PDF) ou baixada (Excel/CSV).

Para criar um relatório novo: escreva uma função ``fn(empresa, filtros) -> Relatorio`` e registre em ``RELATORIOS``.
"""

from __future__ import annotations

import calendar
import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from pessoal.models import Dependente, Funcionario

from . import calculo as c
from .conformidade import _somar_meses, periodos_aquisitivos
from .custo import aliquota_encargos
from .models import Competencia, Ferias, Holerite, ItemHolerite, Rescisao, Rubrica
from .servico import remuneracao_fixa, resumo_encargos, rubricas_por_papel
from .tabelas import tabelas_do_ano

ZERO = Decimal("0")
MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
         "Outubro", "Novembro", "Dezembro"]
MESES_CURTOS = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


# ---------------------------------------------------------------------------
# Estrutura e formatação
# ---------------------------------------------------------------------------
@dataclass
class Coluna:
    titulo: str
    tipo: str = "texto"  # texto | moeda | numero | inteiro | data | pct


@dataclass
class Secao:
    titulo: str = ""
    linhas: list[list] = field(default_factory=list)
    total: list | None = None
    subtitulo: str = ""
    rodape: str = ""
    colunas: list[Coluna] | None = None


@dataclass
class Relatorio:
    titulo: str
    subtitulo: str = ""
    colunas: list[Coluna] = field(default_factory=list)
    secoes: list[Secao] = field(default_factory=list)
    resumo: list[tuple[str, object, str]] = field(default_factory=list)  # (rótulo, valor, tipo)
    notas: list[str] = field(default_factory=list)
    paisagem: bool = False
    vazio: str = "Nenhum dado para os filtros escolhidos."

    @property
    def tem_dados(self) -> bool:
        return any(s.linhas for s in self.secoes)

    def tabelas(self):
        """Seções já formatadas para o template."""
        for s in self.secoes:
            cols = s.colunas or self.colunas
            yield {
                "titulo": s.titulo, "subtitulo": s.subtitulo, "rodape": s.rodape,
                "cabecalho": [(col.titulo, _classe(col.tipo)) for col in cols],
                "linhas": [_formatar_linha(linha, cols) for linha in s.linhas],
                "total": _formatar_linha(s.total, cols) if s.total else None,
            }

    def resumo_formatado(self):
        return [(rotulo, formatar(valor, tipo)) for rotulo, valor, tipo in self.resumo]


def _classe(tipo: str) -> str:
    return "num" if tipo in {"moeda", "numero", "inteiro", "pct"} else ""


def _formatar_linha(linha, cols):
    return [(formatar(v, col.tipo), _classe(col.tipo)) for v, col in zip(linha, cols)]


def _br(valor: Decimal, casas=2, milhar=True) -> str:
    texto = f"{valor:,.{casas}f}" if milhar else f"{valor:.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def formatar(valor, tipo: str, planilha: bool = False) -> str:
    if valor is None or valor == "":
        return ""
    if tipo in {"moeda", "numero"}:
        return _br(Decimal(valor), 2, milhar=not planilha)
    if tipo == "pct":
        return _br(Decimal(valor), 2, milhar=False) + ("" if planilha else "%")
    if tipo == "inteiro":
        return str(valor)
    if tipo == "data" and isinstance(valor, date):
        return f"{valor:%d/%m/%Y}"
    return str(valor)


def para_csv(rel: Relatorio, empresa) -> bytes:
    """CSV no padrão do Excel em português (separador ';', vírgula decimal, UTF-8 com BOM)."""
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";")
    w.writerow([rel.titulo])
    w.writerow([f"{empresa} - {rel.subtitulo}".strip(" -")])
    for rotulo, valor, tipo in rel.resumo:
        w.writerow([rotulo, formatar(valor, tipo, planilha=True)])
    for s in rel.secoes:
        cols = s.colunas or rel.colunas
        w.writerow([])
        if s.titulo:
            w.writerow([s.titulo + (f" - {s.subtitulo}" if s.subtitulo else "")])
        w.writerow([col.titulo for col in cols])
        for linha in s.linhas + ([s.total] if s.total else []):
            w.writerow([formatar(v, col.tipo, planilha=True) for v, col in zip(linha, cols)])
        if s.rodape:
            w.writerow([s.rodape])
    for nota in rel.notas:
        w.writerow([])
        w.writerow([nota])
    return ("﻿" + saida.getvalue()).encode("utf-8")


@dataclass
class Filtros:
    competencia: Competencia | None = None
    ano: int = 0
    mes: int = 0
    funcionario: Funcionario | None = None
    situacao: str = "ativos"


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
def _soma(valores) -> Decimal:
    return sum((v or ZERO for v in valores), ZERO)


def _fim_do_mes(ano: int, mes: int) -> date:
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def _sim_nao(v: bool) -> str:
    return "Sim" if v else "Não"


def _idade(nasc: date, em: date) -> int:
    return em.year - nasc.year - ((em.month, em.day) < (nasc.month, nasc.day))


def _tempo(inicio: date, fim: date) -> str:
    meses = (fim.year - inicio.year) * 12 + fim.month - inicio.month - (fim.day < inicio.day)
    anos, meses = divmod(max(meses, 0), 12)
    partes = []
    if anos:
        partes.append(f"{anos} ano{'s' if anos > 1 else ''}")
    if meses or not anos:
        partes.append(f"{meses} {'mês' if meses == 1 else 'meses'}")
    return " e ".join(partes)


def _sem_competencia() -> Relatorio:
    return Relatorio("Escolha uma folha", vazio="Calcule uma folha mensal para ver este relatório.")


def _holerites(comp: Competencia):
    return comp.holerites.select_related("funcionario__cargo").order_by("funcionario__nome", "tipo", "pk")


def _por_funcionario(holerites):
    grupos: dict[int, list[Holerite]] = defaultdict(list)
    for h in holerites:
        grupos[h.funcionario_id].append(h)
    return [(hs[0].funcionario, hs) for hs in grupos.values()]


def _funcionarios(empresa, f: Filtros):
    qs = Funcionario.objects.filter(empresa=empresa).select_related("cargo").order_by("nome")
    if f.funcionario:
        qs = qs.filter(pk=f.funcionario.pk)
    return qs


# ---------------------------------------------------------------------------
# Folha do mês
# ---------------------------------------------------------------------------
def resumo_folha(empresa, f: Filtros) -> Relatorio:
    comp = f.competencia
    if not comp:
        return _sem_competencia()
    itens = ItemHolerite.objects.filter(holerite__competencia=comp).select_related("rubrica", "holerite")
    por_rubrica: dict[int, dict] = {}
    for i in itens:
        d = por_rubrica.setdefault(i.rubrica_id, {"r": i.rubrica, "func": set(), "valor": ZERO})
        d["func"].add(i.holerite.funcionario_id)
        d["valor"] += i.valor
    grupos = [(1, "Proventos"), (2, "Descontos"), (3, "Informativas")]
    secoes = []
    for tipo, titulo in grupos:
        linhas = [
            [d["r"].codigo, d["r"].descricao, len(d["func"]), d["valor"]]
            for d in sorted(por_rubrica.values(), key=lambda d: d["r"].codigo)
            if (d["r"].tipo if d["r"].tipo < 3 else 3) == tipo
        ]
        if linhas:
            secoes.append(Secao(titulo, linhas, ["", f"Total de {titulo.lower()}", "", _soma(l[3] for l in linhas)]))
    rel = Relatorio(
        "Resumo da folha", str(comp),
        [Coluna("Código"), Coluna("Rubrica"), Coluna("Funcionários", "inteiro"), Coluna("Valor (R$)", "moeda")],
        secoes,
    )
    if comp.holerites.exists():
        r = resumo_encargos(comp)
        rel.resumo = [
            ("Funcionários", r.funcionarios, "inteiro"), ("Proventos", r.total_proventos, "moeda"),
            ("Descontos", r.total_descontos, "moeda"), ("Líquido a pagar", r.total_liquido, "moeda"),
            ("Encargos da empresa (INSS + FGTS)", r.cpp_patronal + r.rat + r.terceiros + r.fgts, "moeda"),
            ("Custo total da folha", r.custo_total_empresa, "moeda"),
        ]
    return rel


def folha_analitica(empresa, f: Filtros) -> Relatorio:
    comp = f.competencia
    if not comp:
        return _sem_competencia()
    hs = _holerites(comp)
    if f.funcionario:
        hs = hs.filter(funcionario=f.funcionario)
    secoes = []
    for h in hs.prefetch_related("itens__rubrica"):
        linhas = []
        for i in sorted(h.itens.all(), key=lambda i: (i.rubrica.tipo, i.rubrica.codigo)):
            if i.rubrica.tipo > 2:
                continue
            prov = i.valor if i.rubrica.tipo == 1 else None
            desc = i.valor if i.rubrica.tipo == 2 else None
            linhas.append([i.rubrica.codigo, i.rubrica.descricao, i.referencia, prov, desc])
        fu = h.funcionario
        secoes.append(Secao(
            f"{fu.matricula} · {fu.nome}",
            linhas,
            ["", f"Líquido: R$ {_br(h.liquido)}", "", h.total_proventos, h.total_descontos],
            subtitulo=f"{h.get_tipo_display()} · {fu.cargo.nome} · {h.dias_trabalhados} dias · "
                      f"salário R$ {_br(h.salario_contratual)}",
            rodape=f"Base INSS R$ {_br(h.base_inss)} · Base IRRF R$ {_br(h.base_irrf)} · "
                   f"Base FGTS R$ {_br(h.base_fgts)} · FGTS do mês R$ {_br(h.valor_fgts)}",
        ))
    return Relatorio(
        "Folha analítica", f"{comp} · todos os holerites, rubrica por rubrica",
        [Coluna("Código"), Coluna("Rubrica"), Coluna("Referência", "numero"),
         Coluna("Proventos (R$)", "moeda"), Coluna("Descontos (R$)", "moeda")],
        secoes,
    )


def relacao_liquidos(empresa, f: Filtros) -> Relatorio:
    comp = f.competencia
    if not comp:
        return _sem_competencia()
    linhas = []
    for h in _holerites(comp):
        fu = h.funcionario
        linhas.append([fu.matricula, fu.nome, fu.cpf_formatado, h.get_tipo_display(), h.data_pagamento,
                       fu.banco, fu.agencia, fu.conta, fu.chave_pix, h.liquido])
    return Relatorio(
        "Relação de líquidos para pagamento", f"{comp} · dados bancários para pagar cada funcionário",
        [Coluna("Matrícula"), Coluna("Nome"), Coluna("CPF"), Coluna("Tipo"), Coluna("Pagar em", "data"),
         Coluna("Banco"), Coluna("Agência"), Coluna("Conta"), Coluna("Chave PIX"), Coluna("Líquido (R$)", "moeda")],
        [Secao(linhas=linhas, total=["", "Total", "", "", "", "", "", "", "", _soma(l[-1] for l in linhas)])],
        paisagem=True,
    )


def relatorio_inss(empresa, f: Filtros) -> Relatorio:
    comp = f.competencia
    if not comp:
        return _sem_competencia()
    linhas = []
    for fu, hs in _por_funcionario(_holerites(comp)):
        base, valor = _soma(h.base_inss for h in hs), _soma(h.valor_inss for h in hs)
        aliq = c.r2(valor * 100 / base) if base else ZERO
        linhas.append([fu.matricula, fu.nome, fu.cpf_formatado, base, valor, aliq,
                       _soma(h.salario_familia for h in hs)])
    total = ["", "Total", "", _soma(l[3] for l in linhas), _soma(l[4] for l in linhas), None,
             _soma(l[6] for l in linhas)]
    rel = Relatorio(
        "Relatório do INSS", str(comp),
        [Coluna("Matrícula"), Coluna("Nome"), Coluna("CPF"), Coluna("Base de cálculo (R$)", "moeda"),
         Coluna("INSS descontado (R$)", "moeda"), Coluna("Alíquota efetiva", "pct"),
         Coluna("Salário-família (R$)", "moeda")],
        [Secao(linhas=linhas, total=total)],
    )
    if linhas:
        r = resumo_encargos(comp)
        rel.resumo = [
            ("INSS dos empregados", r.inss_segurados, "moeda"), ("INSS patronal (CPP)", r.cpp_patronal, "moeda"),
            ("RAT x FAP", r.rat, "moeda"), ("Terceiros", r.terceiros, "moeda"),
            ("(-) Salário-família", r.salario_familia, "moeda"),
            ("Previdência a recolher (DCTFWeb)", r.previdencia_a_recolher, "moeda"),
        ]
        if empresa.optante_simples:
            rel.notas.append("Empresa do Simples Nacional: o INSS patronal e terceiros são pagos no DAS, "
                             "exceto nos anexos IV.")
    return rel


def relatorio_irrf(empresa, f: Filtros) -> Relatorio:
    comp = f.competencia
    if not comp:
        return _sem_competencia()
    linhas = []
    for h in _holerites(comp):
        fu = h.funcionario
        linhas.append([fu.matricula, fu.nome, fu.cpf_formatado, h.get_tipo_display(), h.base_irrf,
                       h.dependentes_irrf, h.reducao_irrf, h.valor_irrf])
    total = ["", "Total", "", "", _soma(l[4] for l in linhas), None, _soma(l[6] for l in linhas),
             _soma(l[7] for l in linhas)]
    return Relatorio(
        "Relatório do IRRF", f"{comp} · imposto de renda retido de cada pagamento",
        [Coluna("Matrícula"), Coluna("Nome"), Coluna("CPF"), Coluna("Pagamento"), Coluna("Base (R$)", "moeda"),
         Coluna("Dependentes", "inteiro"), Coluna("Redução Lei 15.270 (R$)", "moeda"),
         Coluna("IRRF retido (R$)", "moeda")],
        [Secao(linhas=linhas, total=total)],
        notas=["O IRRF entra na DCTFWeb do mês do pagamento (regime de caixa)."],
    )


def relatorio_fgts(empresa, f: Filtros) -> Relatorio:
    comp = f.competencia
    if not comp:
        return _sem_competencia()
    tab = tabelas_do_ano(comp.ano)
    linhas = []
    for fu, hs in _por_funcionario(_holerites(comp)):
        aliq = tab.fgts_aliquota_aprendiz if fu.aprendiz else tab.fgts_aliquota
        linhas.append([fu.matricula, fu.nome, fu.cpf_formatado, _soma(h.base_fgts for h in hs), aliq,
                       _soma(h.valor_fgts for h in hs)])
    total = ["", "Total", "", _soma(l[3] for l in linhas), None, _soma(l[5] for l in linhas)]
    return Relatorio(
        "Relatório do FGTS", str(comp),
        [Coluna("Matrícula"), Coluna("Nome"), Coluna("CPF"), Coluna("Base (R$)", "moeda"),
         Coluna("Alíquota", "pct"), Coluna("FGTS (R$)", "moeda")],
        [Secao(linhas=linhas, total=total)],
        notas=["Pago pela guia do FGTS Digital (GFD) até o dia 20 do mês seguinte. "
               "O FGTS de rescisões tem guia própria."],
    )


def resumo_encargos_guias(empresa, f: Filtros) -> Relatorio:
    comp = f.competencia
    if not comp:
        return _sem_competencia()
    rel = Relatorio("Encargos e guias", f"{comp} · o que a empresa recolhe ao governo",
                    [Coluna("Descrição"), Coluna("Valor (R$)", "moeda")])
    if not comp.holerites.exists():
        return rel
    r = resumo_encargos(comp)
    rel.secoes = [
        Secao("DARF da DCTFWeb (INSS e IRRF)", [
            ["Base de cálculo do INSS", r.base_inss],
            ["INSS descontado dos empregados", r.inss_segurados],
            ["INSS patronal (CPP 20%)", r.cpp_patronal],
            ["RAT ajustado pelo FAP", r.rat],
            ["Terceiros (Sistema S, salário-educação, Incra)", r.terceiros],
            ["(-) Salário-família pago", -r.salario_familia],
            ["IRRF retido", r.irrf],
        ], ["Total estimado do DARF", r.darf_estimado]),
        Secao("FGTS Digital (GFD)", [["Base de cálculo do FGTS", r.base_fgts]], ["FGTS a recolher", r.fgts]),
    ]
    guias = list(comp.guias.all())
    if guias:
        rel.secoes.append(Secao(
            "Guias", [[g.get_tipo_display(), g.vencimento, g.valor_estimado, g.get_status_display()] for g in guias],
            colunas=[Coluna("Guia"), Coluna("Vencimento", "data"), Coluna("Valor (R$)", "moeda"), Coluna("Situação")],
        ))
    rel.resumo = [("DARF DCTFWeb", r.darf_estimado, "moeda"), ("FGTS", r.fgts, "moeda"),
                  ("Total de encargos e retenções", r.darf_estimado + r.fgts, "moeda")]
    rel.notas.append("Valores estimados pela folha. O valor oficial é o da DCTFWeb e do FGTS Digital, "
                     "que leem o que foi enviado ao eSocial.")
    return rel


# ---------------------------------------------------------------------------
# Anuais
# ---------------------------------------------------------------------------
def ficha_financeira(empresa, f: Filtros) -> Relatorio:
    hs = (Holerite.objects.filter(competencia__empresa=empresa, competencia__ano=f.ano)
          .select_related("funcionario", "competencia").prefetch_related("itens__rubrica"))
    if f.funcionario:
        hs = hs.filter(funcionario=f.funcionario)
    # coluna 1..12 = mês; 13 = 13º salário (2ª parcela)
    dados: dict[int, dict] = {}
    for h in hs:
        col = 13 if h.competencia.tipo == "13" else h.competencia.mes
        d = dados.setdefault(h.funcionario_id, {"f": h.funcionario, "rub": defaultdict(lambda: defaultdict(Decimal)),
                                                  "tot": defaultdict(lambda: defaultdict(Decimal))})
        for i in h.itens.all():
            if i.rubrica.tipo <= 2:
                d["rub"][i.rubrica][col] += i.valor
        for campo in ("total_proventos", "total_descontos", "liquido", "base_inss", "base_fgts", "valor_fgts"):
            d["tot"][campo][col] += getattr(h, campo)

    def linha(rotulo, valores):
        cols = [valores.get(m) or None for m in range(1, 14)]
        return [rotulo, *cols, _soma(valores.values())]

    secoes = []
    for d in sorted(dados.values(), key=lambda d: d["f"].nome):
        rubs = sorted(d["rub"], key=lambda r: (r.tipo, r.codigo))
        linhas = [linha(f"{'(-) ' if r.tipo == 2 else ''}{r.codigo} {r.descricao}", d["rub"][r]) for r in rubs]
        linhas += [linha(rot, d["tot"][campo]) for rot, campo in [
            ("Total de proventos", "total_proventos"), ("Total de descontos", "total_descontos"),
            ("Base do INSS", "base_inss"), ("Base do FGTS", "base_fgts"), ("FGTS depositado", "valor_fgts")]]
        fu = d["f"]
        secoes.append(Secao(f"{fu.matricula} · {fu.nome}", linhas, linha("Líquido", d["tot"]["liquido"]),
                            subtitulo=f"CPF {fu.cpf_formatado} · admissão {fu.data_admissao:%d/%m/%Y}"))
    return Relatorio(
        "Ficha financeira", f"Ano de {f.ano} · tudo o que cada funcionário recebeu e teve descontado, mês a mês",
        [Coluna("Rubrica"), *[Coluna(MESES_CURTOS[m], "moeda") for m in range(1, 13)], Coluna("13º", "moeda"),
         Coluna("Total", "moeda")],
        secoes, paisagem=True,
    )


def evolucao_anual(empresa, f: Filtros) -> Relatorio:
    linhas = []
    for comp in Competencia.objects.filter(empresa=empresa, ano=f.ano).order_by("mes", "tipo"):
        if not comp.holerites.exists():
            continue
        r = resumo_encargos(comp)
        rotulo = "13º salário" if comp.tipo == "13" else MESES[comp.mes]
        linhas.append([rotulo, r.funcionarios, r.total_proventos, r.total_descontos, r.total_liquido,
                       r.inss_segurados, r.cpp_patronal + r.rat + r.terceiros, r.irrf, r.fgts,
                       r.custo_total_empresa])
    total = ["Total do ano", None, *[_soma(l[i] for l in linhas) for i in range(2, 10)]]
    rel = Relatorio(
        "Resumo anual da folha", f"Ano de {f.ano} · evolução mês a mês",
        [Coluna("Mês"), Coluna("Funcionários", "inteiro"), Coluna("Proventos (R$)", "moeda"),
         Coluna("Descontos (R$)", "moeda"), Coluna("Líquido (R$)", "moeda"), Coluna("INSS empregados (R$)", "moeda"),
         Coluna("INSS patronal (R$)", "moeda"), Coluna("IRRF (R$)", "moeda"), Coluna("FGTS (R$)", "moeda"),
         Coluna("Custo total (R$)", "moeda")],
        [Secao(linhas=linhas, total=total if linhas else None)], paisagem=True,
    )
    if linhas:
        rel.resumo = [("Proventos no ano", total[2], "moeda"), ("Custo total no ano", total[9], "moeda"),
                      ("Média mensal de custo", c.r2(total[9] / len(linhas)), "moeda")]
    return rel


def informe_rendimentos(empresa, f: Filtros) -> Relatorio:
    """Conferência do comprovante de rendimentos (IN RFB 2.060/2021), pelo regime de caixa."""
    rub_papel = rubricas_por_papel(empresa)
    acum: dict[int, dict] = {}

    def conta(fu):
        return acum.setdefault(fu.pk, {"f": fu, **{k: ZERO for k in (
            "trib", "prev", "irrf", "isento_resc", "isento_abono", "sal_fam", "dec13", "prev13", "irrf13")}})

    def somar(d, rubrica: Rubrica, valor: Decimal):
        v = valor * rubrica.sinal()
        inc = rubrica.inc_irrf
        if inc in {"11", "13"}:
            d["trib"] += v
        elif inc == "12":
            d["dec13"] += v
        elif inc == "41":
            d["prev"] += valor
        elif inc == "42":
            d["prev13"] += valor
        elif inc in {"31", "33"}:
            d["irrf"] += valor
        elif inc == "32":
            d["irrf13"] += valor
        elif inc == "73":
            d["isento_resc"] += v
        elif inc == "74":
            d["isento_abono"] += v
        if rubrica.papel == "salario_familia":
            d["sal_fam"] += valor

    hs = (Holerite.objects.filter(competencia__empresa=empresa, data_pagamento__year=f.ano)
          .select_related("funcionario").prefetch_related("itens__rubrica"))
    if f.funcionario:
        hs = hs.filter(funcionario=f.funcionario)
    for h in hs:
        d = conta(h.funcionario)
        for i in h.itens.all():
            somar(d, i.rubrica, i.valor)
    rescs = Rescisao.objects.filter(funcionario__empresa=empresa, data_pagamento__year=f.ano).exclude(
        status="cancelada").select_related("funcionario")
    if f.funcionario:
        rescs = rescs.filter(funcionario=f.funcionario)
    for resc in rescs:
        d = conta(resc.funcionario)
        for item in resc.itens:
            rubrica = rub_papel.get(item.get("papel"))
            if rubrica:
                somar(d, rubrica, Decimal(item["valor"]))

    secoes = []
    for d in sorted(acum.values(), key=lambda d: d["f"].nome):
        fu = d["f"]
        secoes.append(Secao(f"{fu.nome}", [
            ["3.1", "Total dos rendimentos (inclusive férias)", d["trib"]],
            ["3.2", "Contribuição previdenciária oficial", d["prev"]],
            ["3.5", "Imposto sobre a renda retido na fonte", d["irrf"]],
            ["4.6", "Indenizações por rescisão de contrato de trabalho", d["isento_resc"] or None],
            ["4.7", "Outros isentos: abono pecuniário de férias", d["isento_abono"] or None],
            ["4.7", "Outros isentos: salário-família", d["sal_fam"] or None],
            ["5.1", "13º salário", d["dec13"]],
            ["5.1", "(-) Contribuição previdenciária sobre o 13º", d["prev13"] or None],
            ["5.2", "Imposto sobre a renda retido sobre o 13º", d["irrf13"]],
        ], subtitulo=f"CPF {fu.cpf_formatado} · matrícula {fu.matricula}"))
    return Relatorio(
        "Informe de rendimentos", f"Ano-calendário {f.ano} · pagamentos feitos de janeiro a dezembro",
        [Coluna("Quadro"), Coluna("Descrição"), Coluna("Valor (R$)", "moeda")], secoes,
        notas=["Conferência do comprovante de rendimentos que a empresa entrega até o fim de fevereiro. "
               "Confira com o contador antes de entregar: o valor oficial é o que foi enviado ao eSocial "
               "(eventos S-1210) e à DCTFWeb.",
               "13º salário: informe o valor líquido do INSS no quadro 5, conforme o modelo da Receita."],
    )


def decimo_terceiro(empresa, f: Filtros) -> Relatorio:
    hs = (Holerite.objects.filter(competencia__empresa=empresa, competencia__ano=f.ano, tipo__in=["adiant13", "dec13"])
          .select_related("funcionario").prefetch_related("itens__rubrica"))
    dados: dict[int, dict] = {}
    for h in hs:
        d = dados.setdefault(h.funcionario_id, {"f": h.funcionario, "adiant": ZERO, "integral": ZERO, "inss": ZERO,
                                                  "irrf": ZERO, "desc_adiant": ZERO, "liquido2": ZERO})
        if h.tipo == "adiant13":
            d["adiant"] += h.liquido
        else:
            for i in h.itens.all():
                if i.rubrica.papel == "dec13":
                    d["integral"] += i.valor
                elif i.rubrica.papel == "inss13":
                    d["inss"] += i.valor
                elif i.rubrica.papel == "irrf13":
                    d["irrf"] += i.valor
                elif i.rubrica.papel == "desc_adiant13":
                    d["desc_adiant"] += i.valor
            d["liquido2"] += h.liquido
    linhas = [[d["f"].nome, d["adiant"], d["integral"], d["inss"], d["irrf"], d["desc_adiant"], d["liquido2"]]
              for d in sorted(dados.values(), key=lambda d: d["f"].nome)]
    total = ["Total", *[_soma(l[i] for l in linhas) for i in range(1, 7)]]
    return Relatorio(
        "13º salário", f"Ano de {f.ano} · 1ª parcela (até 30/11) e 2ª parcela (até 20/12)",
        [Coluna("Funcionário"), Coluna("1ª parcela paga (R$)", "moeda"), Coluna("13º integral (R$)", "moeda"),
         Coluna("INSS (R$)", "moeda"), Coluna("IRRF (R$)", "moeda"), Coluna("(-) 1ª parcela (R$)", "moeda"),
         Coluna("Líquido da 2ª parcela (R$)", "moeda")],
        [Secao(linhas=linhas, total=total if linhas else None)],
    )


def provisao_ferias_13(empresa, f: Filtros) -> Relatorio:
    base = _fim_do_mes(f.ano, f.mes or 12)
    tab = tabelas_do_ano(f.ano)
    aliq_enc, _ = aliquota_encargos(empresa)
    linhas = []
    for fu in Funcionario.objects.filter(empresa=empresa, data_admissao__lte=base).select_related("cargo"):
        if fu.data_desligamento and fu.data_desligamento <= base:
            continue
        remun = remuneracao_fixa(fu, tab)
        avos13 = c.avos_13(f.ano, fu.data_admissao, None, ate_mes=base.month)
        prov13 = c.r2(remun * avos13 / 12)
        usados = set(fu.ferias.exclude(status="cancelada").values_list("aquisitivo_inicio", flat=True))
        completos = periodos_aquisitivos(fu.data_admissao, base)
        vencidas = sum(1 for ini, _ in completos if ini not in usados)
        inicio_atual = completos[-1][1] + timedelta(days=1) if completos else fu.data_admissao
        avos_fer = 0
        while avos_fer < 12 and _somar_meses(inicio_atual, avos_fer + 1) - timedelta(days=1) <= base:
            avos_fer += 1
        if avos_fer < 12 and (base - _somar_meses(inicio_atual, avos_fer)).days + 1 >= 15:
            avos_fer += 1
        prov_fer = c.r2(remun * (12 * vencidas + avos_fer) / 12 * 4 / 3)
        aliq_fgts = tab.fgts_aliquota_aprendiz if fu.aprendiz else tab.fgts_aliquota
        encargos = c.r2((prov13 + prov_fer) * (aliq_enc + aliq_fgts) / 100)
        linhas.append([fu.matricula, fu.nome, remun, avos13, prov13, vencidas, avos_fer, prov_fer, encargos,
                       prov13 + prov_fer + encargos])
    linhas.sort(key=lambda l: l[1])
    total = ["", "Total", _soma(l[2] for l in linhas), None, _soma(l[4] for l in linhas), None, None,
             _soma(l[7] for l in linhas), _soma(l[8] for l in linhas), _soma(l[9] for l in linhas)]
    rel = Relatorio(
        "Provisão de férias e 13º", f"Posição em {base:%d/%m/%Y} · quanto a empresa já deve de férias e 13º",
        [Coluna("Matrícula"), Coluna("Nome"), Coluna("Remuneração (R$)", "moeda"), Coluna("Avos 13º", "inteiro"),
         Coluna("Provisão 13º (R$)", "moeda"), Coluna("Férias vencidas", "inteiro"), Coluna("Avos férias", "inteiro"),
         Coluna("Provisão férias + 1/3 (R$)", "moeda"), Coluna("Encargos + FGTS (R$)", "moeda"),
         Coluna("Total (R$)", "moeda")],
        [Secao(linhas=linhas, total=total if linhas else None)], paisagem=True,
        notas=["13º: avos do ano até o mês escolhido, sem descontar o que já foi pago. "
               "Férias: períodos vencidos ainda não programados mais os avos do período em andamento, com 1/3.",
               f"Encargos: {_br(aliq_enc)}% patronais desta empresa + FGTS."],
    )
    if linhas:
        rel.resumo = [("Provisão de 13º", total[4], "moeda"), ("Provisão de férias", total[7], "moeda"),
                      ("Total com encargos", total[9], "moeda")]
    return rel


def controle_ferias(empresa, f: Filtros) -> Relatorio:
    hoje = timezone.localdate()
    pendentes = []
    for fu in Funcionario.objects.filter(empresa=empresa, data_desligamento__isnull=True).order_by("nome"):
        usados = set(fu.ferias.exclude(status="cancelada").values_list("aquisitivo_inicio", flat=True))
        periodos = periodos_aquisitivos(fu.data_admissao, hoje)
        inicio_atual = periodos[-1][1] + timedelta(days=1) if periodos else fu.data_admissao
        periodos.append((inicio_atual, _somar_meses(inicio_atual, 12) - timedelta(days=1)))
        for ini, fim in periodos:
            if ini in usados:
                continue
            limite = _somar_meses(fim + timedelta(days=1), 12) - timedelta(days=1)
            if fim >= hoje:
                situacao = "Em aquisição"
            elif hoje > limite:
                situacao = "VENCIDA: pagar em dobro (CLT art. 137)"
            elif (limite - hoje).days <= 90:
                situacao = f"Atenção: vence em {(limite - hoje).days} dias"
            else:
                situacao = "Pode tirar férias"
            pendentes.append([fu.nome, fu.data_admissao, f"{ini:%d/%m/%Y} a {fim:%d/%m/%Y}", limite, situacao])
    marcadas = [
        [fe.funcionario.nome, f"{fe.aquisitivo_inicio:%d/%m/%Y} a {fe.aquisitivo_fim:%d/%m/%Y}", fe.inicio, fe.fim,
         fe.dias, fe.dias_abono, fe.get_status_display()]
        for fe in Ferias.objects.filter(funcionario__empresa=empresa, inicio__gte=hoje - timedelta(days=30))
        .exclude(status="cancelada").select_related("funcionario").order_by("inicio")
    ]
    return Relatorio(
        "Controle de férias", f"Situação em {hoje:%d/%m/%Y}",
        [Coluna("Funcionário"), Coluna("Admissão", "data"), Coluna("Período aquisitivo"),
         Coluna("Sair de férias até", "data"), Coluna("Situação")],
        [Secao("Períodos sem férias marcadas", pendentes),
         Secao("Férias marcadas e recentes", marcadas, colunas=[
             Coluna("Funcionário"), Coluna("Período aquisitivo"), Coluna("Início", "data"), Coluna("Fim", "data"),
             Coluna("Dias", "inteiro"), Coluna("Dias vendidos", "inteiro"), Coluna("Situação")])],
        notas=["As férias precisam começar dentro dos 12 meses seguintes ao período aquisitivo (CLT art. 134). "
               "O aviso ao funcionário é de pelo menos 30 dias antes (art. 135)."],
    )


def ferias_do_ano(empresa, f: Filtros) -> Relatorio:
    qs = (Ferias.objects.filter(funcionario__empresa=empresa, inicio__year=f.ano).exclude(status="cancelada")
          .select_related("funcionario").order_by("inicio"))
    linhas = [[fe.funcionario.nome, fe.inicio, fe.fim, fe.dias, fe.dias_abono, fe.data_pagamento,
               fe.valor_ferias + fe.valor_terco, fe.valor_abono, fe.valor_inss, fe.valor_irrf, fe.liquido,
               fe.get_status_display()] for fe in qs]
    total = ["Total", None, None, None, None, None, *[_soma(l[i] for l in linhas) for i in range(6, 11)], ""]
    return Relatorio(
        "Férias do ano", f"Férias com início em {f.ano}",
        [Coluna("Funcionário"), Coluna("Início", "data"), Coluna("Fim", "data"), Coluna("Dias", "inteiro"),
         Coluna("Vendidos", "inteiro"), Coluna("Pagamento", "data"), Coluna("Férias + 1/3 (R$)", "moeda"),
         Coluna("Abono (R$)", "moeda"), Coluna("INSS (R$)", "moeda"), Coluna("IRRF (R$)", "moeda"),
         Coluna("Líquido (R$)", "moeda"), Coluna("Situação")],
        [Secao(linhas=linhas, total=total if linhas else None)], paisagem=True,
    )


def rescisoes_do_ano(empresa, f: Filtros) -> Relatorio:
    qs = (Rescisao.objects.filter(funcionario__empresa=empresa, data_desligamento__year=f.ano)
          .exclude(status="cancelada").select_related("funcionario").order_by("data_desligamento"))
    linhas = [[r.funcionario.nome, r.data_desligamento, r.get_motivo_display().split(" - ", 1)[-1], r.data_pagamento,
               r.total_proventos, r.total_descontos, r.liquido, r.fgts_rescisorio, r.multa_fgts] for r in qs]
    total = ["Total", None, "", None, *[_soma(l[i] for l in linhas) for i in range(4, 9)]]
    return Relatorio(
        "Rescisões do ano", f"Desligamentos em {f.ano}",
        [Coluna("Funcionário"), Coluna("Desligamento", "data"), Coluna("Motivo"), Coluna("Pagamento", "data"),
         Coluna("Proventos (R$)", "moeda"), Coluna("Descontos (R$)", "moeda"), Coluna("Líquido (R$)", "moeda"),
         Coluna("FGTS do mês (R$)", "moeda"), Coluna("Multa FGTS (R$)", "moeda")],
        [Secao(linhas=linhas, total=total if linhas else None)], paisagem=True,
    )


# ---------------------------------------------------------------------------
# Pessoas
# ---------------------------------------------------------------------------
def relacao_funcionarios(empresa, f: Filtros) -> Relatorio:
    qs = Funcionario.objects.filter(empresa=empresa).select_related("cargo").order_by("nome")
    if f.situacao == "ativos":
        qs = qs.filter(data_desligamento__isnull=True)
    elif f.situacao == "desligados":
        qs = qs.filter(data_desligamento__isnull=False)
    linhas = [[fu.matricula, fu.nome, fu.cpf_formatado, fu.data_nascimento, fu.cargo.nome, fu.cargo.cbo,
               fu.data_admissao, fu.get_categoria_display().split(" - ", 1)[-1], fu.salario,
               "Ativo" if fu.ativo else f"Desligado em {fu.data_desligamento:%d/%m/%Y}"] for fu in qs]
    rotulo = {"ativos": "ativos", "desligados": "desligados", "todos": "todos"}.get(f.situacao, "ativos")
    return Relatorio(
        "Relação de funcionários", f"Funcionários {rotulo}",
        [Coluna("Matrícula"), Coluna("Nome"), Coluna("CPF"), Coluna("Nascimento", "data"), Coluna("Cargo"),
         Coluna("CBO"), Coluna("Admissão", "data"), Coluna("Categoria"), Coluna("Salário (R$)", "moeda"),
         Coluna("Situação")],
        [Secao(linhas=linhas, total=["", f"{len(linhas)} funcionário(s)", "", None, "", "", None, "",
                                     _soma(l[8] for l in linhas), ""] if linhas else None)],
        paisagem=True,
    )


def admissoes_desligamentos(empresa, f: Filtros) -> Relatorio:
    adm = Funcionario.objects.filter(empresa=empresa, data_admissao__year=f.ano).select_related("cargo")
    desl = Funcionario.objects.filter(empresa=empresa, data_desligamento__year=f.ano).select_related("cargo")
    if f.mes:
        adm, desl = adm.filter(data_admissao__month=f.mes), desl.filter(data_desligamento__month=f.mes)
    periodo = f"{MESES[f.mes]} de {f.ano}" if f.mes else f"Ano de {f.ano}"
    linhas_adm = [[fu.matricula, fu.nome, fu.data_admissao, fu.cargo.nome, fu.salario]
                  for fu in adm.order_by("data_admissao")]
    linhas_desl = [[fu.matricula, fu.nome, fu.data_desligamento,
                    fu.get_motivo_desligamento_display().split(" - ", 1)[-1],
                    _tempo(fu.data_admissao, fu.data_desligamento)] for fu in desl.order_by("data_desligamento")]
    rel = Relatorio(
        "Admissões e desligamentos", periodo,
        secoes=[
            Secao("Admissões", linhas_adm, colunas=[Coluna("Matrícula"), Coluna("Nome"), Coluna("Admissão", "data"),
                                                    Coluna("Cargo"), Coluna("Salário (R$)", "moeda")]),
            Secao("Desligamentos", linhas_desl, colunas=[Coluna("Matrícula"), Coluna("Nome"),
                                                         Coluna("Desligamento", "data"), Coluna("Motivo"),
                                                         Coluna("Tempo de casa")]),
        ],
    )
    rel.resumo = [("Admissões", len(linhas_adm), "inteiro"), ("Desligamentos", len(linhas_desl), "inteiro"),
                  ("Saldo", len(linhas_adm) - len(linhas_desl), "inteiro")]
    return rel


def aniversariantes(empresa, f: Filtros) -> Relatorio:
    mes = f.mes or timezone.localdate().month
    qs = Funcionario.objects.filter(empresa=empresa, data_desligamento__isnull=True,
                                    data_nascimento__month=mes).select_related("cargo")
    hoje = timezone.localdate()
    linhas = [[fu.data_nascimento.day, fu.nome, fu.cargo.nome, fu.data_nascimento,
               _idade(fu.data_nascimento, date(hoje.year, mes, min(fu.data_nascimento.day,
                                                                   calendar.monthrange(hoje.year, mes)[1])))]
              for fu in sorted(qs, key=lambda fu: (fu.data_nascimento.day, fu.nome))]
    casa = [[fu.data_admissao.day, fu.nome, fu.cargo.nome, fu.data_admissao, hoje.year - fu.data_admissao.year]
            for fu in Funcionario.objects.filter(empresa=empresa, data_desligamento__isnull=True,
                                                 data_admissao__month=mes, data_admissao__year__lt=hoje.year)
            .select_related("cargo").order_by("data_admissao__day", "nome")]
    return Relatorio(
        "Aniversariantes", MESES[mes],
        [Coluna("Dia", "inteiro"), Coluna("Nome"), Coluna("Cargo"), Coluna("Nascimento", "data"),
         Coluna("Idade que completa", "inteiro")],
        [Secao("Aniversário", linhas),
         Secao("Tempo de empresa", casa, colunas=[Coluna("Dia", "inteiro"), Coluna("Nome"), Coluna("Cargo"),
                                                   Coluna("Admissão", "data"), Coluna("Anos de casa", "inteiro")])],
    )


def relacao_dependentes(empresa, f: Filtros) -> Relatorio:
    hoje = timezone.localdate()
    qs = (Dependente.objects.filter(funcionario__empresa=empresa, funcionario__data_desligamento__isnull=True)
          .select_related("funcionario").order_by("funcionario__nome", "nome"))
    linhas = [[d.funcionario.nome, d.nome, d.get_tipo_display().split(" ")[0], d.data_nascimento,
               _idade(d.data_nascimento, hoje), _sim_nao(d.dependente_irrf),
               _sim_nao(d.da_direito_salario_familia(hoje))] for d in qs]
    return Relatorio(
        "Dependentes", "Dependentes dos funcionários ativos",
        [Coluna("Funcionário"), Coluna("Dependente"), Coluna("Parentesco"), Coluna("Nascimento", "data"),
         Coluna("Idade", "inteiro"), Coluna("Deduz no IRRF"), Coluna("Salário-família hoje")],
        [Secao(linhas=linhas)],
        notas=["Salário-família: filhos até 14 anos (ou inválidos) de quem ganha até o limite do ano, "
               "com certidão de nascimento e vacinação/frequência escolar em dia."],
    )


def contratos_a_vencer(empresa, f: Filtros) -> Relatorio:
    hoje = timezone.localdate()
    qs = (Funcionario.objects.filter(empresa=empresa, data_desligamento__isnull=True, data_termino__isnull=False)
          .select_related("cargo").order_by("data_termino"))
    linhas = []
    for fu in qs:
        dias = (fu.data_termino - hoje).days
        situacao = "Vencido" if dias < 0 else ("Vence hoje" if dias == 0 else f"Faltam {dias} dias")
        linhas.append([fu.nome, fu.cargo.nome, fu.get_tipo_contrato_display(), fu.data_admissao, fu.data_termino,
                       situacao])
    return Relatorio(
        "Contratos a vencer", "Experiência e prazo determinado",
        [Coluna("Funcionário"), Coluna("Cargo"), Coluna("Contrato"), Coluna("Admissão", "data"),
         Coluna("Término", "data"), Coluna("Situação")],
        [Secao(linhas=linhas)],
        notas=["Contrato de experiência: no máximo 90 dias, com uma prorrogação (CLT art. 445). "
               "Se o funcionário continuar trabalhando depois do término, o contrato vira por prazo indeterminado."],
        vazio="Nenhum funcionário ativo com data de término de contrato.",
    )


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
@dataclass
class Tipo:
    slug: str
    titulo: str
    grupo: str
    descricao: str
    filtros: tuple[str, ...]
    funcao: object


RELATORIOS = [
    Tipo("resumo-folha", "Resumo da folha", "Folha do mês",
         "Totais por rubrica (salários, horas extras, descontos) e o custo da folha.", ("competencia",), resumo_folha),
    Tipo("folha-analitica", "Folha analítica", "Folha do mês",
         "Cada holerite com todas as rubricas, bases e FGTS. É a folha completa para arquivar.",
         ("competencia", "funcionario"), folha_analitica),
    Tipo("liquidos", "Relação de líquidos", "Folha do mês",
         "Quanto pagar a cada um, com banco, conta e PIX. Use para fazer os pagamentos.",
         ("competencia",), relacao_liquidos),
    Tipo("inss", "INSS", "Folha do mês",
         "Base e desconto de cada funcionário e o INSS da empresa a recolher.", ("competencia",), relatorio_inss),
    Tipo("irrf", "Imposto de renda (IRRF)", "Folha do mês",
         "Base, dependentes e imposto retido de cada pagamento.", ("competencia",), relatorio_irrf),
    Tipo("fgts", "FGTS", "Folha do mês", "Base e depósito do FGTS de cada funcionário.", ("competencia",),
         relatorio_fgts),
    Tipo("encargos", "Encargos e guias", "Folha do mês",
         "Composição do DARF (DCTFWeb) e do FGTS Digital, com vencimentos.", ("competencia",),
         resumo_encargos_guias),
    Tipo("ficha-financeira", "Ficha financeira", "Anuais",
         "Tudo que cada funcionário recebeu no ano, mês a mês e rubrica por rubrica.", ("ano", "funcionario"),
         ficha_financeira),
    Tipo("resumo-anual", "Resumo anual da folha", "Anuais",
         "Proventos, encargos e custo total de cada mês do ano.", ("ano",), evolucao_anual),
    Tipo("informe-rendimentos", "Informe de rendimentos", "Anuais",
         "Conferência do comprovante para o imposto de renda dos funcionários.", ("ano", "funcionario"),
         informe_rendimentos),
    Tipo("13-salario", "13º salário", "Anuais", "1ª e 2ª parcelas, INSS e IRRF do 13º de cada funcionário.",
         ("ano",), decimo_terceiro),
    Tipo("ferias-ano", "Férias do ano", "Anuais", "Férias gozadas e programadas no ano, com valores pagos.",
         ("ano",), ferias_do_ano),
    Tipo("rescisoes", "Rescisões do ano", "Anuais", "Desligamentos com verbas, FGTS e multa.", ("ano",),
         rescisoes_do_ano),
    Tipo("provisao", "Provisão de férias e 13º", "Controle",
         "Quanto a empresa já deve de férias e 13º, com encargos. Útil para a contabilidade.", ("ano", "mes"),
         provisao_ferias_13),
    Tipo("controle-ferias", "Controle de férias", "Controle",
         "Períodos vencidos, a vencer e férias marcadas. Evita pagar férias em dobro.", (), controle_ferias),
    Tipo("contratos", "Contratos a vencer", "Controle", "Contratos de experiência e prazo determinado.", (),
         contratos_a_vencer),
    Tipo("funcionarios", "Relação de funcionários", "Pessoas",
         "Lista com CPF, cargo, CBO, admissão e salário.", ("situacao",), relacao_funcionarios),
    Tipo("admissoes-desligamentos", "Admissões e desligamentos", "Pessoas",
         "Quem entrou e quem saiu no período (turnover).", ("ano", "mes_opcional"), admissoes_desligamentos),
    Tipo("aniversariantes", "Aniversariantes", "Pessoas", "Aniversários e tempo de empresa do mês.", ("mes",),
         aniversariantes),
    Tipo("dependentes", "Dependentes", "Pessoas", "Dependentes para IRRF e salário-família.", (),
         relacao_dependentes),
]
POR_SLUG = {t.slug: t for t in RELATORIOS}
GRUPOS = ["Folha do mês", "Anuais", "Controle", "Pessoas"]
