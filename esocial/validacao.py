"""Validação dos XMLs contra os schemas (XSD) oficiais do eSocial."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from django.conf import settings
from lxml import etree

from .xml_eventos import EVENTOS

PASTA_SCHEMAS = Path(__file__).resolve().parent / "schemas"


@lru_cache(maxsize=None)
def _schema(arquivo: str) -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(PASTA_SCHEMAS / arquivo)))


def schema_evento(tipo: str) -> etree.XMLSchema:
    nome, _ = EVENTOS[tipo]
    return _schema(f"{settings.ESOCIAL_VERSAO_LAYOUT}/{nome}.xsd")


def erros_xsd(xml: bytes | etree._Element, schema: etree.XMLSchema) -> list[str]:
    doc = etree.fromstring(xml) if isinstance(xml, (bytes, str)) else xml
    if schema.validate(doc):
        return []
    return [f"linha {e.line}: {e.message}" for e in schema.error_log]


_FALTA_ASSINATURA = "Expected is ( {http://www.w3.org/2000/09/xmldsig#}Signature )"


def validar_evento(tipo: str, xml, assinado: bool = True) -> list[str]:
    """Valida no XSD. Com ``assinado=False`` ignora a falta da assinatura (validação prévia)."""
    erros = erros_xsd(xml, schema_evento(tipo))
    if not assinado:
        erros = [e for e in erros if _FALTA_ASSINATURA not in e]
    return erros


def validar_lote(xml) -> list[str]:
    return erros_xsd(xml, _schema("comunicacao/EnvioLoteEventos-v1_1_1.xsd"))
