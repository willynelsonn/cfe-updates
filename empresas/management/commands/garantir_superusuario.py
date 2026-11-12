"""Cria o primeiro usuário ou acerta a senha dele com os valores do ambiente (usado na nuvem).

Lê DJANGO_SUPERUSER_USERNAME e DJANGO_SUPERUSER_PASSWORD. Assim, trocar a senha no painel do
Render e publicar de novo troca a senha de entrada no sistema.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Cria o superusuário ou atualiza a senha dele a partir das variáveis de ambiente."

    def handle(self, *args, **opts):
        nome = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        senha = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        if not nome or not senha:
            self.stdout.write("DJANGO_SUPERUSER_USERNAME/PASSWORD não definidos; nada a fazer.")
            return
        usuario, criado = get_user_model().objects.get_or_create(username=nome)
        usuario.is_staff = usuario.is_superuser = usuario.is_active = True
        usuario.set_password(senha)
        usuario.save()
        self.stdout.write(f"Usuário {nome} {'criado' if criado else 'com a senha atualizada'}.")
