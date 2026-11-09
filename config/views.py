from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from esocial.models import Evento
from esocial.servico import situacao_fila
from folha.conformidade import verificar
from folha.models import Competencia, Ferias


@login_required
def dashboard(request):
    empresa = request.empresa
    ctx = {}
    if empresa:
        hoje = timezone.localdate()
        funcionarios = empresa.funcionarios
        ctx = {
            "hoje": hoje,
            "ativos": funcionarios.filter(data_desligamento__isnull=True).count(),
            "competencia": Competencia.objects.filter(empresa=empresa, tipo="mensal").first(),
            "fila": situacao_fila(empresa),
            "alertas": verificar(empresa, hoje),
            "proximas_ferias": Ferias.objects.filter(
                funcionario__empresa=empresa, inicio__gte=hoje, status="calculada"
            ).select_related("funcionario")[:5],
            "iniciais_ok": empresa.esocial_ja_iniciado
            or Evento.objects.filter(empresa=empresa, tipo="S-1000", status="aceito").exists(),
        }
    return render(request, "dashboard.html", ctx)
