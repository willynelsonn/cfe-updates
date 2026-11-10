"""Cria o arquivo .env de produção (uma vez só), com chave secreta aleatória."""

import secrets

from django.conf import settings
from django.core.management.base import BaseCommand

MODELO = """# Configuração do FolhaWeb neste servidor. Gerado por "manage.py preparar_servidor".
# NÃO compartilhe este arquivo: a chave abaixo protege as senhas dos certificados digitais.
FOLHA_SECRET_KEY={chave}
FOLHA_DEBUG=false

# Endereços aceitos. O ".trycloudflare.com" é o endereço provisório do Cloudflare Tunnel.
# Com domínio próprio, acrescente-o aqui e em FOLHA_CSRF_TRUSTED_ORIGINS (ex.: folha.seudominio.com.br).
FOLHA_ALLOWED_HOSTS=localhost,127.0.0.1,.trycloudflare.com
FOLHA_CSRF_TRUSTED_ORIGINS=https://*.trycloudflare.com

# Endereço fixo (opcional): crie um túnel em one.dash.cloudflare.com > Networks > Tunnels,
# aponte o domínio para http://localhost:8000 e cole o token do túnel aqui.
FOLHA_CLOUDFLARE_TOKEN=

# Cor padrão do sistema: laranja, azul, verde, roxo, rosa ou grafite.
FOLHA_COR_PADRAO=grafite
"""


class Command(BaseCommand):
    help = "Cria o .env de produção com uma chave secreta aleatória, se ainda não existir."

    def handle(self, *args, **opts):
        caminho = settings.BASE_DIR / ".env"
        if caminho.exists():
            self.stdout.write("Arquivo .env já existe; nada a fazer.")
            return
        caminho.write_text(MODELO.format(chave=secrets.token_urlsafe(50)), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Criado {caminho} com uma chave secreta nova."))
