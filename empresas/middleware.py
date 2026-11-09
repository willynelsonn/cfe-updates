from .models import Empresa


class EmpresaAtivaMiddleware:
    """Disponibiliza ``request.empresa`` com a empresa selecionada na sessão."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.empresa = None
        if getattr(request, "user", None) and request.user.is_authenticated:
            empresa_id = request.session.get("empresa_id")
            empresa = Empresa.objects.filter(pk=empresa_id, ativa=True).first() if empresa_id else None
            if empresa is None:
                empresa = Empresa.objects.filter(ativa=True).first()
                if empresa:
                    request.session["empresa_id"] = empresa.pk
            request.empresa = empresa
        return self.get_response(request)
