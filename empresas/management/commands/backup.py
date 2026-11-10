"""Cópia de segurança do banco (SQLite) e dos certificados digitais.

Gera backups/folhaweb-AAAAMMDD-HHMM.zip e mantém só os mais recentes.
    python manage.py backup            # faz o backup
    python manage.py backup --manter 60
"""

import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Faz backup do banco de dados e dos certificados digitais na pasta backups/."

    def add_arguments(self, parser):
        parser.add_argument("--manter", type=int, default=30, help="Quantos backups guardar (padrão 30).")
        parser.add_argument("--pasta", default=str(settings.BASE_DIR / "backups"))

    def handle(self, *args, **opts):
        banco = settings.DATABASES["default"]
        if banco["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("Banco PostgreSQL: use o pg_dump do próprio PostgreSQL para o backup.")
        pasta = Path(opts["pasta"])
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / f"folhaweb-{datetime.now():%Y%m%d-%H%M}.zip"
        with tempfile.TemporaryDirectory() as tmp:
            copia = Path(tmp) / "db.sqlite3"
            # API de backup do SQLite: cópia consistente mesmo com o sistema em uso.
            origem = sqlite3.connect(str(banco["NAME"]))
            alvo = sqlite3.connect(str(copia))
            with alvo:
                origem.backup(alvo)
            origem.close()
            alvo.close()
            with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(copia, "db.sqlite3")
                privado = Path(settings.PRIVATE_MEDIA_ROOT)
                if privado.exists():
                    for arq in privado.rglob("*"):
                        if arq.is_file():
                            z.write(arq, Path("private_media") / arq.relative_to(privado))
                env = settings.BASE_DIR / ".env"
                if env.exists():
                    # Sem o .env (FOLHA_SECRET_KEY) não dá para ler as senhas dos certificados.
                    z.write(env, ".env")
        antigos = sorted(pasta.glob("folhaweb-*.zip"))[: -opts["manter"]]
        for a in antigos:
            a.unlink()
        self.stdout.write(self.style.SUCCESS(f"Backup salvo em {destino}"))
