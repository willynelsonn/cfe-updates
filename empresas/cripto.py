"""Criptografia simétrica para guardar a senha do certificado digital no banco."""

import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    chave = hashlib.sha256(("folhaweb-cert:" + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(chave))


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode() if texto else ""


def decifrar(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode() if token else ""
