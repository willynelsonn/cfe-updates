from .models import Empresa


def empresa_ativa(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    return {
        "empresa_ativa": getattr(request, "empresa", None),
        "empresas_disponiveis": Empresa.objects.filter(ativa=True).only("id", "razao_social", "nome_fantasia"),
    }
