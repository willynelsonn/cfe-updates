"""Configurações do FolhaWeb.

Valores sensíveis vêm de variáveis de ambiente (veja .env.example).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "sim", "yes", "on"}


SECRET_KEY = os.environ.get(
    "FOLHA_SECRET_KEY",
    # Chave apenas para desenvolvimento. Em produção, defina FOLHA_SECRET_KEY.
    "dev-insegura-troque-em-producao-0123456789abcdefghijklmnopqrstuvwxyz",
)
DEBUG = env_bool("FOLHA_DEBUG", True)
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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# SQLite por padrão; para produção use PostgreSQL definindo FOLHA_DB_* .
if os.environ.get("FOLHA_DB_ENGINE") == "postgres":
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

# Certificados A1 (.pfx) ficam fora da pasta pública.
PRIVATE_MEDIA_ROOT = Path(os.environ.get("FOLHA_PRIVATE_MEDIA", BASE_DIR / "private_media"))

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

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
