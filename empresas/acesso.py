"""Quem é do escritório e o que a dona (cliente) pode ver."""

from .models import Empresa

# Únicos caminhos que quem não é do escritório pode abrir; todo o resto é bloqueado por padrão.
ROTAS_DA_CLIENTE = (
    "/cliente/", "/sair/", "/conta/", "/static/", "/cadastro/", "/convite/", "/termos/", "/privacidade/",
)


def eh_escritorio(user) -> bool:
    return bool(user and user.is_authenticated and user.is_staff)


def empresas_do_usuario(user):
    """Empresas que a dona pode ver no portal (qualquer situação: em análise, ativa ou recusada)."""
    return Empresa.objects.filter(acessos__usuario=user)
