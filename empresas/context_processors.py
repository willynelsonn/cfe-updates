from django.utils.functional import SimpleLazyObject

from .models import Empresa


def _criticos(request):
    from folha.conformidade import CRITICO, verificar

    if not request.empresa:
        return 0
    return sum(1 for a in verificar(request.empresa) if a.nivel == CRITICO)


def empresa_ativa(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    return {
        "empresa_ativa": getattr(request, "empresa", None),
        "empresas_disponiveis": Empresa.objects.filter(ativa=True).only("id", "razao_social", "nome_fantasia"),
        "pendencias_criticas": SimpleLazyObject(lambda: _criticos(request)),
    }
