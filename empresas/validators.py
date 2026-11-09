"""Validação de CPF e CNPJ (inclusive o CNPJ alfanumérico, vigente a partir de 07/2026)."""

import re

from django.core.exceptions import ValidationError


def so_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def normalizar_cnpj(valor: str) -> str:
    """Remove pontuação e coloca em maiúsculas (CNPJ pode ter letras nas 12 primeiras posições)."""
    return re.sub(r"[^0-9A-Za-z]", "", valor or "").upper()


def cpf_valido(cpf: str) -> bool:
    cpf = so_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        dv = (soma * 10) % 11 % 10
        if dv != int(cpf[tamanho]):
            return False
    return True


def _valor_cnpj(c: str) -> int:
    # Regra do CNPJ alfanumérico: valor = código ASCII - 48 (dígitos continuam iguais).
    return ord(c) - 48


def cnpj_valido(cnpj: str) -> bool:
    cnpj = normalizar_cnpj(cnpj)
    if not re.fullmatch(r"[A-Z0-9]{12}\d{2}", cnpj) or cnpj == cnpj[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, pos in ((pesos1, 12), (pesos2, 13)):
        soma = sum(_valor_cnpj(cnpj[i]) * pesos[i] for i in range(pos))
        resto = soma % 11
        dv = 0 if resto < 2 else 11 - resto
        if dv != int(cnpj[pos]):
            return False
    return True


def validar_cpf(valor):
    if not cpf_valido(valor):
        raise ValidationError("CPF inválido.")


def validar_cnpj(valor):
    if not cnpj_valido(valor):
        raise ValidationError("CNPJ inválido.")


def formatar_cpf(cpf: str) -> str:
    c = so_digitos(cpf)
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}" if len(c) == 11 else cpf


def formatar_cnpj(cnpj: str) -> str:
    c = normalizar_cnpj(cnpj)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else cnpj
