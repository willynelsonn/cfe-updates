"""Liga um domínio próprio ao FolhaWeb pelo Cloudflare Tunnel (usado pelo ConfigurarDominio.bat).

    python manage.py configurar_dominio folha.seudominio.com.br --credenciais tools/tunel-credenciais.json

Grava tools/cloudflared.yml (túnel -> http://127.0.0.1:8000), libera o domínio no .env
e salva o endereço em ENDERECO.txt.
"""

import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

DOMINIO_VALIDO = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def normalizar_dominio(texto: str) -> str:
    d = texto.strip().lower()
    d = re.sub(r"^https?://", "", d).split("/")[0].split(":")[0]
    if not DOMINIO_VALIDO.match(d):
        raise CommandError(f"Endereço inválido: {texto!r}. Exemplo: folha.seudominio.com.br")
    return d


def acrescentar_no_env(caminho: Path, chave: str, valor: str) -> None:
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    for i, linha in enumerate(linhas):
        if linha.split("=", 1)[0].strip() == chave:
            atuais = [v.strip() for v in linha.split("=", 1)[1].split(",") if v.strip()]
            if valor not in atuais:
                atuais.append(valor)
            linhas[i] = f"{chave}={','.join(atuais)}"
            break
    else:
        linhas.append(f"{chave}={valor}")
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")


class Command(BaseCommand):
    help = "Configura o endereço fixo (domínio próprio) do FolhaWeb no Cloudflare Tunnel."

    def add_arguments(self, parser):
        parser.add_argument("dominio")
        parser.add_argument("--credenciais", required=True, help="Arquivo JSON criado por 'cloudflared tunnel create'.")
        parser.add_argument("--porta", type=int, default=8000)

    def handle(self, *args, **opts):
        dominio = normalizar_dominio(opts["dominio"])
        credenciais = Path(opts["credenciais"]).resolve()
        try:
            tunel_id = json.loads(credenciais.read_text(encoding="utf-8"))["TunnelID"]
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(f"Não foi possível ler as credenciais do túnel em {credenciais}: {exc}") from exc

        base = Path(settings.BASE_DIR)
        (base / "tools").mkdir(exist_ok=True)
        (base / "tools" / "cloudflared.yml").write_text(
            f"# Gerado por ConfigurarDominio.bat. Para voltar ao endereço provisório, apague este arquivo.\n"
            f"tunnel: {tunel_id}\n"
            f"credentials-file: {json.dumps(str(credenciais))}\n"
            f"ingress:\n"
            f"  - hostname: {dominio}\n"
            f"    service: http://127.0.0.1:{opts['porta']}\n"
            f"  - service: http_status:404\n",
            encoding="utf-8",
        )
        env = base / ".env"
        if not env.exists():
            call_command("preparar_servidor", stdout=self.stdout)
        acrescentar_no_env(env, "FOLHA_ALLOWED_HOSTS", dominio)
        acrescentar_no_env(env, "FOLHA_CSRF_TRUSTED_ORIGINS", f"https://{dominio}")
        (base / "ENDERECO.txt").write_text(f"https://{dominio}\n", encoding="ascii")
        self.stdout.write(self.style.SUCCESS(f"Pronto: o FolhaWeb vai responder em https://{dominio}"))
