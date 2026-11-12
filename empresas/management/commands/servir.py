"""Servidor de produção (Waitress), que funciona no Windows e no Linux.

No próprio servidor escuta só em 127.0.0.1 (quem publica é o Cloudflare Tunnel):
    python manage.py servir --porta 8000
Na nuvem (Render), atrás do proxy da hospedagem:
    python manage.py servir --host 0.0.0.0 --nuvem      (a porta vem da variável PORT)
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Inicia o FolhaWeb em modo de produção com o servidor Waitress."

    def add_arguments(self, parser):
        parser.add_argument("--porta", type=int, default=int(os.environ.get("PORT", 8000)))
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--threads", type=int, default=8)
        parser.add_argument("--nuvem", action="store_true",
                            help="Confia no proxy da hospedagem (HTTPS e IP real do visitante).")

    def handle(self, *args, **opts):
        from waitress import serve

        from config.wsgi import application

        if settings.DEBUG:
            self.stderr.write(self.style.WARNING("Atenção: FOLHA_DEBUG está ligado. Use o .env de produção."))
        self.stdout.write(self.style.SUCCESS(f"FolhaWeb em http://{opts['host']}:{opts['porta']} (Ctrl+C para parar)"))
        if opts["nuvem"]:
            proxy = {"trusted_proxy": "*", "trusted_proxy_count": 1,
                     "trusted_proxy_headers": {"x-forwarded-proto", "x-forwarded-for"}}
        else:
            proxy = {"trusted_proxy": "127.0.0.1", "trusted_proxy_headers": {"x-forwarded-proto"}}
        serve(application, host=opts["host"], port=opts["porta"], threads=opts["threads"],
              clear_untrusted_proxy_headers=True, **proxy)
