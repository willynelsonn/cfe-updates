from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from .acesso import ROTAS_DA_CLIENTE, eh_escritorio, empresas_do_usuario
from .models import Empresa


class EmpresaAtivaMiddleware:
    """Disponibiliza ``request.empresa`` com a empresa selecionada na sessão."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.empresa = None
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            # Escritório escolhe entre as ativas; a dona, só entre as dela (nunca "a primeira do sistema").
            permitidas = Empresa.objects.filter(ativa=True) if eh_escritorio(user) else empresas_do_usuario(user)
            empresa_id = request.session.get("empresa_id")
            empresa = permitidas.filter(pk=empresa_id).first() if empresa_id else None
            if empresa is None:
                empresa = permitidas.first()
                if empresa:
                    request.session["empresa_id"] = empresa.pk
            request.empresa = empresa
        return self.get_response(request)


class PortalMiddleware:
    """Bloqueio por padrão: quem não é do escritório só abre as rotas do portal."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and not eh_escritorio(user) and not request.path.startswith(ROTAS_DA_CLIENTE):
            if request.method in ("GET", "HEAD"):
                return redirect("/cliente/")
            return HttpResponseForbidden("Esta área é do escritório.")
        return self.get_response(request)
