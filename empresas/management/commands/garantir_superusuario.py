"""Cria o primeiro usuário com os valores do ambiente (usado na nuvem a cada publicação).

Lê DJANGO_SUPERUSER_USERNAME e DJANGO_SUPERUSER_PASSWORD. Se o usuário já existe, a senha dele
só é trocada quando FOLHA_REDEFINIR_SENHA=sim. Assim a senha alterada pela tela "Alterar senha"
não volta a ser a do painel do Render a cada publicação.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Cria o superusuário a partir das variáveis de ambiente (e redefine a senha se pedido)."

    def handle(self, *args, **opts):
        nome = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        senha = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        if not nome or not senha:
            self.stdout.write("DJANGO_SUPERUSER_USERNAME/PASSWORD não definidos; nada a fazer.")
            return
        redefinir = os.environ.get("FOLHA_REDEFINIR_SENHA", "").strip().lower() in {"1", "true", "sim", "yes", "on"}
        usuario, criado = get_user_model().objects.get_or_create(username=nome)
        if not criado and not redefinir:
            self.stdout.write(f"Usuário {nome} já existe; senha mantida.")
            return
        usuario.is_staff = usuario.is_superuser = usuario.is_active = True
        usuario.set_password(senha)
        usuario.save()
        self.stdout.write(f"Usuário {nome} {'criado' if criado else 'com a senha redefinida'}.")
