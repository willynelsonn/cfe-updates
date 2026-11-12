"""Configurações do FolhaWeb.

Valores sensíveis vêm de variáveis de ambiente (veja .env.example).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _carregar_env(caminho: Path) -> None:
    """Lê KEY=VALOR de um arquivo .env (sem sobrescrever variáveis já definidas no sistema)."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


_carregar_env(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "sim", "yes", "on"}


SECRET_KEY = os.environ.get(
    "FOLHA_SECRET_KEY",
    # Chave apenas para desenvolvimento. Em produção, defina FOLHA_SECRET_KEY.
    "dev-insegura-troque-em-producao-0123456789abcdefghijklmnopqrstuvwxyz",
)
DEBUG = env_bool("FOLHA_DEBUG", True)
if not DEBUG and SECRET_KEY.startswith("dev-insegura"):
    raise RuntimeError("Defina FOLHA_SECRET_KEY no arquivo .env antes de rodar em produção.")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("FOLHA_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("FOLHA_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "empresas",
    "pessoal",
    "folha",
    "esocial",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "empresas.middleware.EmpresaAtivaMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "empresas.context_processors.empresa_ativa",
                "empresas.context_processors.aparencia",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Banco de dados:
#  - FOLHA_DATABASE_URL (ou DATABASE_URL): endereço completo do PostgreSQL, como o do Supabase
#    (postgresql://usuario:senha@host:5432/postgres). Usado na nuvem.
#  - FOLHA_DB_ENGINE=postgres + FOLHA_DB_*: PostgreSQL informado por partes.
#  - Sem nada: SQLite no arquivo db.sqlite3 (uso no próprio computador).
# Espaços, quebras de linha e aspas coladas junto do endereço são ignorados.
DATABASE_URL = (os.environ.get("FOLHA_DATABASE_URL") or os.environ.get("DATABASE_URL", "")).strip().strip("\"'`").strip()


def _banco_pela_url(url: str) -> dict:
    from urllib.parse import parse_qs, unquote, urlparse

    u = urlparse(url)
    if u.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError(
            "FOLHA_DATABASE_URL deve começar com postgresql:// "
            "(cole o endereço inteiro do Supabase, com a senha no lugar de [YOUR-PASSWORD])."
        )
    opcoes = {k: v[-1] for k, v in parse_qs(u.query).items()}
    opcoes.setdefault("sslmode", "require")
    banco = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(u.path.lstrip("/")) or "postgres",
        "USER": unquote(u.username or ""),
        "PASSWORD": unquote(u.password or ""),
        "HOST": u.hostname or "",
        "PORT": str(u.port or 5432),
        "OPTIONS": opcoes,
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
    if u.port == 6543:
        # Pooler do Supabase em modo "transaction": sem conexões persistentes nem cursores no servidor.
        banco["CONN_MAX_AGE"] = 0
        banco["DISABLE_SERVER_SIDE_CURSORS"] = True
    return banco


if DATABASE_URL:
    DATABASES = {"default": _banco_pela_url(DATABASE_URL)}
elif os.environ.get("FOLHA_DB_ENGINE") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("FOLHA_DB_NAME", "folha"),
            "USER": os.environ.get("FOLHA_DB_USER", "folha"),
            "PASSWORD": os.environ.get("FOLHA_DB_PASSWORD", ""),
            "HOST": os.environ.get("FOLHA_DB_HOST", "localhost"),
            "PORT": os.environ.get("FOLHA_DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Comprimido (gzip/brotli) e servido pelo próprio sistema (WhiteNoise), sem servidor web extra.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Certificados A1 (.pfx) ficam fora da pasta pública.
PRIVATE_MEDIA_ROOT = Path(os.environ.get("FOLHA_PRIVATE_MEDIA", BASE_DIR / "private_media"))
# Na nuvem o disco é apagado a cada atualização: os certificados ficam dentro do banco.
FOLHA_ARQUIVOS_NO_BANCO = env_bool("FOLHA_ARQUIVOS_NO_BANCO", bool(DATABASE_URL))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# eSocial
ESOCIAL_VERSAO_LAYOUT = "v_S_01_03_00"
ESOCIAL_VER_PROC = "FolhaWeb-0.1"
ESOCIAL_TIMEOUT = int(os.environ.get("FOLHA_ESOCIAL_TIMEOUT", "60"))
# Os servidores do eSocial usam a cadeia ICP-Brasil. Se o sistema operacional não a
# reconhecer, aponte aqui um arquivo .pem com as ACs raiz/intermediárias da ICP-Brasil.
ESOCIAL_CA_BUNDLE = os.environ.get("FOLHA_ESOCIAL_CA_BUNDLE", "")

# Integra Contador (SERPRO) — emissão automática do DARF da DCTFWeb. Serviço pago e opcional.
INTEGRA_CONTADOR = {
    "key": os.environ.get("FOLHA_INTEGRA_KEY", ""),
    "secret": os.environ.get("FOLHA_INTEGRA_SECRET", ""),
    "contratante": os.environ.get("FOLHA_INTEGRA_CONTRATANTE", ""),
    "servico_darf": os.environ.get("FOLHA_INTEGRA_SERVICO_DARF", "GERARGUIA31"),
    "url_autenticacao": os.environ.get("FOLHA_INTEGRA_URL_AUTH", "https://autenticacao.sapi.serpro.gov.br/authenticate"),
    "url_api": os.environ.get("FOLHA_INTEGRA_URL_API", "https://gateway.apiserpro.serpro.gov.br/integra-contador/v1"),
}
FGTS_DIGITAL_URL = "https://fgtsdigital.sistema.gov.br/portal/login"
ECAC_URL = "https://cav.receita.fazenda.gov.br/autenticacao/login"

# Sessão expira após 8 horas e ao fechar o navegador.
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Bloqueio de tentativas de login (por usuário e por IP)
LOGIN_TENTATIVAS_MAX = int(os.environ.get("FOLHA_LOGIN_TENTATIVAS", "5"))
LOGIN_BLOQUEIO_MINUTOS = int(os.environ.get("FOLHA_LOGIN_BLOQUEIO_MIN", "15"))

if not DEBUG:
    # Atrás do Cloudflare Tunnel o HTTPS termina na Cloudflare, que avisa pelo X-Forwarded-Proto.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
    SECURE_HSTS_SECONDS = int(os.environ.get("FOLHA_HSTS_SEGUNDOS", "0"))
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"arquivo": {"class": "logging.FileHandler", "filename": BASE_DIR / "folhaweb.log", "encoding": "utf-8"}},
        "root": {"handlers": ["arquivo"], "level": "WARNING"},
    }

# Cor do sistema usada quando o usuário ainda não escolheu outra no menu da conta.
# Opções: laranja, azul, verde, roxo, rosa, grafite.
FOLHA_COR_PADRAO = os.environ.get("FOLHA_COR_PADRAO", "grafite")
