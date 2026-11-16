"""Dados inventados para os testes do portal (o repositório é público)."""

from django.contrib.auth.models import User

from empresas.models import Acesso
from folha.tests.fabrica import empresa


def dona(emp, email="dona@exemplo.com", senha="Senha-da-dona-2026") -> User:
    u = User.objects.create_user(email, email=email, password=senha, first_name="Dona")
    Acesso.objects.create(usuario=u, empresa=emp, termos_versao="teste")
    return u


def usar_banco_nos_anexos(caso):
    """Anexos dos testes vão para o banco (desfeito a cada teste), como na nuvem; nunca para a pasta private_media."""
    from unittest import mock

    from empresas.armazenamento import BancoStorage
    from portal.models import Anexo

    p = mock.patch.object(Anexo._meta.get_field("arquivo"), "storage", BancoStorage())
    p.start()
    caso.addCleanup(p.stop)


def duas_empresas():
    a = empresa(razao_social="Empresa A LTDA", nr_insc="11.222.333/0001-81")
    b = empresa(razao_social="Empresa B LTDA", nr_insc="42.127.447/0001-76")
    return a, b
