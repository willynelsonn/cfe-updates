from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from esocial.servico import situacao_fila
from folha import painel
from folha.conformidade import CRITICO, verificar
from folha.models import Competencia, Ferias, Guia


@login_required
def dashboard(request):
    empresa = request.empresa
    if not empresa:
        return render(request, "dashboard.html", {})
    hoje = timezone.localdate()
    dados = painel.dados(empresa)
    alertas = verificar(empresa, hoje)
    fila = situacao_fila(empresa)
    total_ev = fila["pendentes"] + fila["enviados"] + fila["aceitos"] + fila["problemas"]
    guias = list(Guia.objects.filter(empresa=empresa, vencimento__gte=hoje - timedelta(days=60))
                 .exclude(status="paga").order_by("vencimento"))
    hora = timezone.localtime().hour
    aberta = Competencia.objects.filter(empresa=empresa, tipo="mensal").exclude(status="fechada").first()
    dados.update({
        "saudacao": "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite",
        "alertas": alertas,
        "criticos": sum(1 for a in alertas if a.nivel == CRITICO),
        "fila": fila,
        "pct_aceitos": (fila["aceitos"] / total_ev * 100) if total_ev else 0,
        "total_eventos": total_ev,
        "guias_abertas": guias,
        "a_pagar": sum((g.valor_estimado for g in guias), 0),
        "proximo_venc": guias[0].vencimento if guias else None,
        "competencia_aberta": aberta,
        "ultima_competencia": Competencia.objects.filter(empresa=empresa, tipo="mensal").first(),
        "proximas_ferias": Ferias.objects.filter(funcionario__empresa=empresa, inicio__gte=hoje, status="calculada")
        .select_related("funcionario")[:4],
        "hc_valores": [m["ativos"] for m in dados["headcount"]],
        "serie_folha": {
            "titulo": "Custo da folha por mês",
            "series": [
                {"chave": "remuneracao", "nome": "Remuneração bruta", "cor": "--s1"},
                {"chave": "encargos", "nome": "Encargos patronais", "cor": "--s2"},
                {"chave": "fgts", "nome": "FGTS", "cor": "--s3"},
            ],
            "pontos": [{"rotulo": m["rotulo"], "valores": {k: m[k] for k in ("remuneracao", "encargos", "fgts")}}
                       for m in dados["folha_serie"]],
        },
    })
    return render(request, "dashboard.html", dados)
