"""Guias de recolhimento: DARF da DCTFWeb e GFD do FGTS Digital.

Ambas são montadas pelo governo a partir do eSocial. Por isso uma guia só fica "pronta
para emitir" quando o fechamento (S-1299) da competência foi ACEITO.
"""

from __future__ import annotations

from datetime import date

from esocial.assinatura import ErroCertificado

from . import calculo as c
from .models import Competencia, Guia
from .servico import resumo_encargos


def vencimentos(competencia: Competencia) -> dict[str, date]:
    if competencia.decimo_terceiro:
        # Contribuições sobre o 13º: dia 20 de dezembro. FGTS da 2ª parcela: com a folha de dezembro (20/01).
        return {
            "darf": c.dia_util_anterior(date(competencia.ano, 12, 20)),
            "fgts": c.vencimento_dia_20(competencia.ano, 12),
        }
    venc = c.vencimento_dia_20(competencia.ano, competencia.mes)
    return {"darf": venc, "fgts": venc}


def fechamento_aceito(competencia: Competencia) -> bool:
    from esocial.models import Evento

    return Evento.objects.filter(
        competencia=competencia, tipo="S-1299", status="aceito"
    ).exists()


def atualizar_guias(competencia: Competencia) -> list[Guia]:
    """Cria/atualiza as guias previstas da competência com valores estimados e vencimentos."""
    if not competencia.holerites.exists():
        return []
    resumo = resumo_encargos(competencia)
    venc = vencimentos(competencia)
    pronta = fechamento_aceito(competencia)
    guias = []
    for tipo, valor in (("darf", resumo.darf_estimado), ("fgts", resumo.fgts)):
        guia, _ = Guia.objects.get_or_create(
            competencia=competencia, tipo=tipo,
            defaults={"empresa": competencia.empresa, "vencimento": venc[tipo]},
        )
        guia.valor_estimado = valor
        guia.vencimento = venc[tipo]
        if guia.status in {"prevista", "disponivel"}:
            guia.status = "disponivel" if pronta else "prevista"
        guia.save()
        guias.append(guia)
    return guias


def emitir_darf(guia: Guia) -> Guia:
    """Emite o DARF pela API Integra Contador (se contratada). Senão, orienta a emissão no e-CAC."""
    from esocial import integra_contador
    from esocial.servico import ErroESocial, certificado_da_empresa

    comp = guia.competencia
    if not fechamento_aceito(comp):
        guia.mensagem = "Aguarde o eSocial aceitar o fechamento (S-1299) desta competência."
        guia.save()
        return guia
    if not integra_contador.configurado():
        guia.mensagem = (
            "Emissão automática não contratada. Emita no e-CAC: DCTFWeb → período "
            f"{comp} → Emitir DARF. Para automatizar, contrate o Integra Contador (SERPRO)."
        )
        guia.save()
        return guia
    try:
        cert = certificado_da_empresa(comp.empresa)
        resultado = integra_contador.emitir_darf_dctfweb(
            comp.empresa, comp.ano, comp.mes, comp.decimo_terceiro, cert
        )
    except (integra_contador.ErroIntegraContador, ErroESocial, ErroCertificado) as exc:
        guia.status, guia.mensagem = "erro", str(exc)
        guia.save()
        return guia
    guia.pdf = resultado.pdf
    guia.status = "emitida"
    guia.mensagem = "; ".join(resultado.mensagens) or "DARF emitido pelo Integra Contador."
    guia.save()
    return guia
