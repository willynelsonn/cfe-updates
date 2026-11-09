from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from esocial.models import Evento, Lote
from folha.models import Competencia


@login_required
def dashboard(request):
    empresa = request.empresa
    ctx = {}
    if empresa:
        funcionarios = empresa.funcionarios
        ctx = {
            "ativos": funcionarios.filter(data_desligamento__isnull=True).count(),
            "competencia": Competencia.objects.filter(empresa=empresa).first(),
            "pendentes": Evento.objects.filter(empresa=empresa, status="pendente").count(),
            "rejeitados": Evento.objects.filter(empresa=empresa, status__in=["rejeitado", "erro"]).count(),
            "aguardando": Lote.objects.filter(empresa=empresa, status="enviado").count(),
            "iniciais_enviados": Evento.objects.filter(empresa=empresa, tipo="S-1000").exists(),
            "sem_admissao": funcionarios.filter(data_desligamento__isnull=True).exclude(evento__tipo="S-2200").count(),
        }
    return render(request, "dashboard.html", ctx)
