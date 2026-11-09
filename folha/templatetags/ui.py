"""Componentes de interface: ícones e formatação de valores."""

from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def icone(nome, classe=""):
    return format_html('<svg class="icon {}" aria-hidden="true"><use href="#i-{}"></use></svg>', classe, nome)


def _dec(valor):
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None


@register.filter
def moeda(valor, casas=2):
    """1234.5 -> 'R$ 1.234,50'"""
    v = _dec(valor)
    if v is None:
        return "—"
    texto = f"{abs(v):,.{int(casas)}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if v < 0 else ''}R$ {texto}"


@register.filter
def numero(valor, casas=2):
    """casas="0" mostra até 2 casas só quando necessário (36 -> 36; 7.5 -> 7,50)."""
    v = _dec(valor)
    if v is None:
        return "—"
    casas = int(casas)
    if casas == 0 and v != v.to_integral_value():
        casas = 2
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


@register.filter
def compacto(valor):
    """12900 -> 'R$ 12,9 mil'; 4200000 -> 'R$ 4,2 mi'"""
    v = _dec(valor)
    if v is None:
        return "—"
    if abs(v) >= 1_000_000:
        return f"R$ {v / 1_000_000:.1f} mi".replace(".", ",")
    if abs(v) >= 10_000:
        return f"R$ {v / 1000:.1f} mil".replace(".", ",")
    return moeda(v)


@register.filter
def iniciais(nome):
    partes = [p for p in str(nome).split() if len(p) > 2 or p.isupper()]
    return "".join(p[0] for p in (partes[:1] + partes[-1:] if len(partes) > 1 else partes)).upper() or "?"


@register.filter
def pct(valor, casas=1):
    v = _dec(valor)
    return "—" if v is None else f"{v:.{int(casas)}f}%".replace(".", ",")
