from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from empresas.acesso import eh_escritorio
from empresas.validators import formatar_cnpj


@login_required
def inicio(request):
    if eh_escritorio(request.user):
        return redirect("dashboard")
    return render(request, "portal/inicio.html", {
        "empresa": request.empresa,
        "escritorio_cnpj": formatar_cnpj(settings.FOLHA_ESCRITORIO_CNPJ),
        "escritorio_nome": settings.FOLHA_ESCRITORIO_NOME,
    })
