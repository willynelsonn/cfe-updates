"""Dados do painel inicial (dashboard)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from pessoal.models import Funcionario

from . import calculo as c
from .conformidade import _somar_meses
from .custo import custos_da_empresa
from .models import Competencia, Ferias, Guia, Rescisao
from .servico import resumo_encargos

ZERO = Decimal("0")
MESES = "jan fev mar abr mai jun jul ago set out nov dez".split()


def _rotulo(d: date) -> str:
    return f"{MESES[d.month - 1]}/{str(d.year)[2:]}"


def headcount_serie(empresa, hoje: date, meses: int = 12) -> list[dict]:
    funcs = list(Funcionario.objects.filter(empresa=empresa).values("data_admissao", "data_desligamento"))
    serie = []
    for i in range(meses - 1, -1, -1):
        ref = _somar_meses(date(hoje.year, hoje.month, 1), -i)
        fim = _somar_meses(ref, 1) - timedelta(days=1)
        ativos = sum(1 for f in funcs if f["data_admissao"] <= fim
                     and (f["data_desligamento"] is None or f["data_desligamento"] >= fim))
        adm = sum(1 for f in funcs if ref <= f["data_admissao"] <= fim)
        desl = sum(1 for f in funcs if f["data_desligamento"] and ref <= f["data_desligamento"] <= fim)
        serie.append({"rotulo": _rotulo(ref), "ativos": ativos, "admissoes": adm, "desligamentos": desl})
    return serie


def custo_folha_serie(empresa, hoje: date, meses: int = 12) -> list[dict]:
    """Desembolso por competência mensal: remuneração bruta, encargos patronais e FGTS."""
    comps = {(cp.ano, cp.mes): cp for cp in Competencia.objects.filter(empresa=empresa, tipo="mensal")
             .exclude(status="aberta")}
    serie = []
    for i in range(meses - 1, -1, -1):
        ref = _somar_meses(date(hoje.year, hoje.month, 1), -i)
        cp = comps.get((ref.year, ref.month))
        if cp is None:
            serie.append({"rotulo": _rotulo(ref), "remuneracao": None, "encargos": None, "fgts": None})
            continue
        r = resumo_encargos(cp)
        serie.append({
            "rotulo": _rotulo(ref), "competencia": cp.pk,
            "remuneracao": float(r.total_proventos),
            "encargos": float(r.cpp_patronal + r.rat + r.terceiros),
            "fgts": float(r.fgts),
        })
    return serie


def agenda(empresa, hoje: date, dias: int = 45) -> list[dict]:
    """Próximos compromissos com prazo legal."""
    limite = hoje + timedelta(days=dias)
    itens = []
    for g in Guia.objects.filter(empresa=empresa, vencimento__lte=limite).exclude(status="paga") \
            .select_related("competencia"):
        itens.append({"data": g.vencimento, "titulo": f"Pagar {g.get_tipo_display()}",
                      "detalhe": f"{g.competencia} · R$ {g.valor_estimado:,.2f}".replace(",", "X").replace(".", ",")
                      .replace("X", "."), "url": reverse("folha:guias", args=[g.competencia_id]), "tipo": "guia"})
    for fe in Ferias.objects.filter(funcionario__empresa=empresa, status="calculada",
                                    data_pagamento__gte=hoje, data_pagamento__lte=limite).select_related("funcionario"):
        itens.append({"data": fe.data_pagamento, "titulo": f"Pagar férias de {fe.funcionario.nome}",
                      "detalhe": f"Gozo a partir de {fe.inicio:%d/%m}",
                      "url": reverse("folha:ferias_detalhe", args=[fe.pk]), "tipo": "ferias"})
    for r in Rescisao.objects.filter(funcionario__empresa=empresa, status="calculada",
                                     data_pagamento__gte=hoje, data_pagamento__lte=limite).select_related("funcionario"):
        itens.append({"data": r.data_pagamento, "titulo": f"Pagar rescisão de {r.funcionario.nome}",
                      "detalhe": f"Prazo legal {r.prazo_pagamento:%d/%m}",
                      "url": reverse("folha:rescisao_detalhe", args=[r.pk]), "tipo": "rescisao"})
    # Prazos fixos do mês
    dia15 = date(hoje.year, hoje.month, 15)
    if hoje <= dia15:
        itens.append({"data": dia15, "titulo": "Enviar a folha do mês anterior ao eSocial",
                      "detalhe": "S-1200, S-1210 e S-1299", "url": reverse("folha:competencias"), "tipo": "esocial"})
    quinto = c.quinto_dia_util(hoje.year, hoje.month)
    if hoje <= quinto:
        itens.append({"data": quinto, "titulo": "Pagar os salários", "detalhe": "5º dia útil (CLT art. 459)",
                      "url": reverse("folha:competencias"), "tipo": "salario"})
    if hoje.month <= 11 and hoje <= date(hoje.year, 11, 30) <= limite:
        itens.append({"data": date(hoje.year, 11, 30), "titulo": "1ª parcela do 13º salário", "detalhe": "Lei 4.749/1965",
                      "url": reverse("folha:competencias"), "tipo": "13"})
    if hoje <= date(hoje.year, 12, 20) <= limite:
        itens.append({"data": c.dia_util_anterior(date(hoje.year, 12, 20)), "titulo": "2ª parcela do 13º salário",
                      "detalhe": "e DARF do 13º", "url": reverse("folha:decimo_terceiro"), "tipo": "13"})
    for it in itens:
        it["dias"] = (it["data"] - hoje).days
    return sorted(itens, key=lambda x: x["data"])


def dados(empresa) -> dict:
    hoje = timezone.localdate()
    custos = custos_da_empresa(empresa)
    total_custo = sum((cu.total for _, cu in custos), ZERO)
    total_rem = sum((cu.remuneracao for _, cu in custos), ZERO)
    grupos: dict[str, Decimal] = defaultdict(lambda: ZERO)
    nomes = {}
    for _, cu in custos:
        for chave, nome, valor in cu.grupos:
            grupos[chave] += valor
            nomes[chave] = nome
    composicao = [{"chave": k, "nome": nomes[k], "valor": float(grupos[k]),
                   "pct": float(grupos[k] / total_custo * 100) if total_custo else 0}
                  for k in ("remuneracao", "encargos", "fgts", "provisoes", "beneficios") if k in grupos]
    por_cargo: dict[str, list] = defaultdict(lambda: [ZERO, 0])
    for f, cu in custos:
        por_cargo[f.cargo.nome][0] += cu.total
        por_cargo[f.cargo.nome][1] += 1
    cargos = sorted(({"cargo": k, "valor": float(v[0]), "pessoas": v[1]} for k, v in por_cargo.items()),
                    key=lambda x: x["valor"], reverse=True)[:8]

    hc = headcount_serie(empresa, hoje)
    folha = custo_folha_serie(empresa, hoje)
    com_dados = [m for m in folha if m["remuneracao"] is not None]
    ultima = com_dados[-1] if com_dados else None
    anterior = com_dados[-2] if len(com_dados) > 1 else None
    total_ultima = (ultima["remuneracao"] + ultima["encargos"] + ultima["fgts"]) if ultima else None
    total_anterior = (anterior["remuneracao"] + anterior["encargos"] + anterior["fgts"]) if anterior else None
    delta = ((total_ultima - total_anterior) / total_anterior * 100) if total_ultima and total_anterior else None
    desligamentos_12m = sum(m["desligamentos"] for m in hc)
    media_hc = sum(m["ativos"] for m in hc) / len(hc) if hc else 0
    return {
        "hoje": hoje,
        "ativos": hc[-1]["ativos"] if hc else 0,
        "admissoes_mes": hc[-1]["admissoes"] if hc else 0,
        "desligamentos_mes": hc[-1]["desligamentos"] if hc else 0,
        "turnover_12m": (desligamentos_12m / media_hc * 100) if media_hc else 0,
        "headcount": hc,
        "custo_mensal": total_custo,
        "custo_medio": (total_custo / len(custos)) if custos else ZERO,
        "multiplicador": (total_custo / total_rem).quantize(Decimal("0.01")) if total_rem else ZERO,
        "composicao": composicao,
        "cargos": cargos,
        "folha_serie": folha,
        "ultima_folha": ultima,
        "ultima_folha_total": total_ultima,
        "variacao_folha": delta,
        "agenda": agenda(empresa, hoje),
    }
