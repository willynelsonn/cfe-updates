from django.conf import settings
from django.utils.functional import SimpleLazyObject

from .acesso import eh_escritorio, empresas_do_usuario
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
        "empresas_disponiveis": (
            Empresa.objects.filter(ativa=True) if eh_escritorio(request.user) else empresas_do_usuario(request.user)
        ).only("id", "razao_social", "nome_fantasia"),
        "pendencias_criticas": SimpleLazyObject(lambda: _criticos(request)),
        # Número de verdade (não preguiçoso): o filtro pluralize precisa de um int.
        "empresas_para_conferir": (
            Empresa.objects.filter(situacao="em_analise").count() if eh_escritorio(request.user) else 0
        ),
    }


CORES = {"laranja", "azul", "verde", "roxo", "rosa", "grafite"}


def aparencia(request):
    cor = getattr(settings, "FOLHA_COR_PADRAO", "laranja")
    ctx = {"cor_padrao": cor if cor in CORES else "laranja"}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        from .models import Preferencia

        ctx["preferencia"] = Preferencia.objects.filter(usuario=user).first()
    return ctx
