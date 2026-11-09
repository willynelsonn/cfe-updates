"""Orquestra geração, assinatura, envio e consulta dos eventos do eSocial."""

from __future__ import annotations

from datetime import date

from django.db import transaction
from django.utils import timezone
from lxml import etree

from folha.models import Competencia, Rubrica, criar_rubricas_padrao

from . import xml_eventos as xe
from .assinatura import Certificado, assinar, carregar_pfx
from .models import Evento, Lote
from .validacao import validar_evento, validar_lote
from .webservice import MAX_EVENTOS_LOTE, ErroWebservice, consultar_lote, enviar_lote, montar_lote


class ErroESocial(Exception):
    pass


def _registrar(empresa, tipo, descricao, id_evento, root, **extra) -> Evento:
    xml = xe.para_bytes(root)
    erros = validar_evento(tipo, xml, assinado=False)
    return Evento.objects.create(
        empresa=empresa,
        tipo=tipo,
        descricao=descricao,
        id_evento=id_evento,
        xml=xml.decode(),
        status="erro" if erros else "pendente",
        mensagens=[f"Schema: {e}" for e in erros],
        **extra,
    )


def _validar_empresa(empresa):
    faltando = []
    if not empresa.cnae or len(empresa.cnae) != 7:
        faltando.append("CNAE")
    if not empresa.fpas:
        faltando.append("FPAS")
    if faltando:
        raise ErroESocial(f"Complete o cadastro da empresa: {', '.join(faltando)}.")


# ---------------------------------------------------------------------------
# Geração
# ---------------------------------------------------------------------------
@transaction.atomic
def gerar_eventos_iniciais(empresa) -> list[Evento]:
    """S-1000, S-1005, S-1020 e S-1010 de todas as rubricas ativas."""
    _validar_empresa(empresa)
    criar_rubricas_padrao(empresa)
    eventos = [
        _registrar(empresa, "S-1000", "Informações do empregador", *xe.s1000(empresa)),
        _registrar(empresa, "S-1005", "Estabelecimento matriz", *xe.s1005(empresa)),
        _registrar(empresa, "S-1020", f"Lotação {empresa.cod_lotacao_padrao}", *xe.s1020(empresa)),
    ]
    for rub in Rubrica.objects.filter(empresa=empresa, ativa=True):
        eventos.append(_registrar(empresa, "S-1010", f"Rubrica {rub}", *xe.s1010(empresa, rub)))
    return eventos


def gerar_admissao(funcionario) -> Evento:
    if not funcionario.empresa.cnpj_sindicato:
        raise ErroESocial("Informe o CNPJ do sindicato no cadastro da empresa (obrigatório no S-2200).")
    return _registrar(
        funcionario.empresa, "S-2200", f"Admissão de {funcionario.nome}", *xe.s2200(funcionario),
        funcionario=funcionario,
    )


def gerar_desligamento(funcionario) -> Evento:
    if not funcionario.data_desligamento or not funcionario.motivo_desligamento:
        raise ErroESocial("Informe a data e o motivo do desligamento no cadastro do funcionário.")
    return _registrar(
        funcionario.empresa, "S-2299", f"Desligamento de {funcionario.nome}", *xe.s2299(funcionario),
        funcionario=funcionario,
    )


@transaction.atomic
def fechar_competencia(competencia: Competencia, transmitir_dctfweb: bool = False) -> list[Evento]:
    """Gera S-1200 (um por trabalhador), S-1210 (pagamentos) e S-1299 (fechamento).

    O S-1210 pertence ao mês do PAGAMENTO. Se o salário é pago no mês seguinte
    (ex.: 5º dia útil), o S-1210 fica no período seguinte e o S-1299 desta
    competência é gerado com evtPgtos = N. O fechamento do mês do pagamento
    informará evtPgtos = S.
    """
    if competencia.status != "calculada":
        raise ErroESocial("Calcule a folha antes de fechar a competência.")
    empresa = competencia.empresa
    holerites = list(competencia.holerites.select_related("funcionario", "competencia"))
    if not holerites:
        raise ErroESocial("Nenhum holerite calculado nesta competência.")

    eventos = []
    for h in holerites:
        eventos.append(
            _registrar(
                empresa, "S-1200", f"Remuneração {competencia} - {h.funcionario.nome}", *xe.s1200(h),
                funcionario=h.funcionario, competencia=competencia, per_apur=competencia.per_apur,
            )
        )

    per_pgto = competencia.data_pagamento.strftime("%Y-%m")
    for cpf, id_evento, root in xe.s1210(empresa, per_pgto, holerites, competencia.data_pagamento):
        func = next(h.funcionario for h in holerites if h.funcionario.cpf == cpf)
        eventos.append(
            _registrar(
                empresa, "S-1210", f"Pagamento {competencia} - {func.nome}", id_evento, root,
                funcionario=func, competencia=competencia, per_apur=per_pgto,
            )
        )

    # Pagamentos de competências anteriores feitos dentro deste mês também contam.
    tem_pgtos = per_pgto == competencia.per_apur or Evento.objects.filter(
        empresa=empresa, tipo="S-1210", per_apur=competencia.per_apur
    ).exists()
    eventos.append(
        _registrar(
            empresa, "S-1299", f"Fechamento {competencia}",
            *xe.s1299(empresa, competencia.per_apur, True, tem_pgtos, transmitir_dctfweb),
            competencia=competencia, per_apur=competencia.per_apur,
        )
    )
    competencia.status = "fechada"
    competencia.save(update_fields=["status"])
    return eventos


# ---------------------------------------------------------------------------
# Envio e consulta
# ---------------------------------------------------------------------------
def certificado_da_empresa(empresa) -> Certificado:
    if not empresa.tem_certificado:
        raise ErroESocial("Cadastre o certificado digital A1 (.pfx) e a senha na empresa.")
    with empresa.certificado.open("rb") as fh:
        return carregar_pfx(fh.read(), empresa.senha_certificado)


def _assinar_evento(evento: Evento, cert: Certificado) -> etree._Element:
    root = etree.fromstring(evento.xml.encode())
    assinado = assinar(root, cert)
    evento.xml_assinado = etree.tostring(assinado, encoding="unicode")
    return assinado


ORDEM_GRUPOS = (1, 2, 3)  # tabelas -> não periódicos -> periódicos


def transmitir_pendentes(empresa) -> list[Lote]:
    """Assina e envia os eventos pendentes, em lotes de até 50, por grupo."""
    cert = certificado_da_empresa(empresa)
    lotes = []
    pendentes = list(Evento.objects.filter(empresa=empresa, status="pendente").order_by("criado_em", "pk"))
    for grupo in ORDEM_GRUPOS:
        do_grupo = [e for e in pendentes if e.grupo == grupo]
        if grupo == 3:
            # O S-1299 precisa ir depois dos S-1200/S-1210 do mesmo período.
            do_grupo.sort(key=lambda e: e.tipo == "S-1299")
        for i in range(0, len(do_grupo), MAX_EVENTOS_LOTE):
            lotes.append(_enviar(empresa, grupo, do_grupo[i : i + MAX_EVENTOS_LOTE], cert))
    return lotes


def _enviar(empresa, grupo, eventos: list[Evento], cert: Certificado) -> Lote:
    assinados = [(ev.id_evento, _assinar_evento(ev, cert)) for ev in eventos]
    lote_xml = montar_lote(grupo, empresa, assinados)
    erros = validar_lote(lote_xml)
    lote = Lote.objects.create(
        empresa=empresa, grupo=grupo, ambiente=empresa.ambiente_esocial,
        xml_envio=etree.tostring(lote_xml, encoding="unicode"),
    )
    if erros:
        lote.status, lote.desc_resposta = "erro", "; ".join(erros)
        lote.save()
        return lote
    try:
        ret = enviar_lote(empresa.ambiente_esocial, lote_xml, cert)
    except ErroWebservice as exc:
        lote.status, lote.desc_resposta = "erro", str(exc)
        lote.save()
        return lote
    lote.xml_retorno_envio = ret.xml.decode(errors="replace")
    lote.cd_resposta, lote.desc_resposta, lote.protocolo = ret.cd_resposta, ret.desc_resposta, ret.protocolo
    lote.status = "enviado" if ret.aceito else "rejeitado"
    lote.save()
    for ev in eventos:
        ev.lote = lote
        if ret.aceito:
            ev.status = "enviado"
        else:
            ev.mensagens = [f"Lote recusado: {ret.cd_resposta} {ret.desc_resposta}", *ret.ocorrencias]
        ev.save()
    return lote


def consultar_lotes_enviados(empresa) -> list[Lote]:
    cert = certificado_da_empresa(empresa)
    atualizados = []
    for lote in Lote.objects.filter(empresa=empresa, status="enviado").exclude(protocolo=""):
        try:
            ret = consultar_lote(lote.ambiente, lote.protocolo, cert)
        except ErroWebservice as exc:
            lote.desc_resposta = str(exc)
            lote.save(update_fields=["desc_resposta"])
            continue
        lote.xml_retorno_consulta = ret.xml.decode(errors="replace")
        lote.consultado_em = timezone.now()
        lote.cd_resposta, lote.desc_resposta = ret.cd_resposta, ret.desc_resposta
        if not ret.em_processamento:
            lote.status = "processado"
            por_id = {r.id_evento: r for r in ret.eventos}
            for ev in lote.eventos.all():
                r = por_id.get(ev.id_evento)
                if r is None:
                    continue
                ev.status = "aceito" if r.sucesso else "rejeitado"
                ev.recibo = r.recibo
                ev.mensagens = [f"{r.cd_resposta} {r.desc_resposta}", *r.ocorrencias]
                ev.save()
        lote.save()
        atualizados.append(lote)
    return atualizados


def reenviar(evento: Evento) -> Evento:
    """Volta um evento rejeitado/erro para a fila (depois de corrigido o cadastro, gere um novo)."""
    if evento.status in {"rejeitado", "erro"}:
        evento.status = "pendente"
        evento.lote = None
        evento.save()
    return evento


def data_pagamento_padrao(ano: int, mes: int, dia: int = 5) -> date:
    """Dia ``dia`` do mês seguinte (ajuste manual para o 5º dia útil se necessário)."""
    proximo_ano, proximo_mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return date(proximo_ano, proximo_mes, min(dia, 28))
