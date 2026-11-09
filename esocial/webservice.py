"""Comunicação com os webservices SOAP do eSocial (envio e consulta de lotes)."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field

import requests
from django.conf import settings
from lxml import etree

from .assinatura import Certificado

URLS = {
    # 1 = produção, 2 = produção restrita
    1: {
        "envio": "https://webservices.envio.esocial.gov.br/servicos/empregador/enviarloteeventos/WsEnviarLoteEventos.svc",
        "consulta": "https://webservices.consulta.esocial.gov.br/servicos/empregador/consultarloteeventos/WsConsultarLoteEventos.svc",
    },
    2: {
        "envio": "https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/enviarloteeventos/WsEnviarLoteEventos.svc",
        "consulta": "https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/consultarloteeventos/WsConsultarLoteEventos.svc",
    },
}

NS_LOTE = "http://www.esocial.gov.br/schema/lote/eventos/envio/v1_1_1"
NS_CONSULTA = "http://www.esocial.gov.br/schema/lote/eventos/envio/consulta/retornoProcessamento/v1_0_0"
NS_WS_ENVIO = "http://www.esocial.gov.br/servicos/empregador/lote/eventos/envio/v1_1_0"
NS_WS_CONSULTA = "http://www.esocial.gov.br/servicos/empregador/lote/eventos/envio/consulta/retornoProcessamento/v1_1_0"
SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"

ACTION_ENVIO = f"{NS_WS_ENVIO}/ServicoEnviarLoteEventos/EnviarLoteEventos"
ACTION_CONSULTA = f"{NS_WS_CONSULTA}/ServicoConsultarLoteEventos/ConsultarLoteEventos"

MAX_EVENTOS_LOTE = 50


class ErroWebservice(Exception):
    pass


# ---------------------------------------------------------------------------
# Montagem
# ---------------------------------------------------------------------------
def montar_lote(grupo: int, empresa, eventos: list[tuple[str, etree._Element]]) -> etree._Element:
    """``eventos`` = [(id_evento, xml_assinado_raiz)]"""
    if not 1 <= len(eventos) <= MAX_EVENTOS_LOTE:
        raise ErroWebservice(f"Um lote deve ter de 1 a {MAX_EVENTOS_LOTE} eventos.")
    E = lambda tag: f"{{{NS_LOTE}}}{tag}"  # noqa: E731
    root = etree.Element(E("eSocial"), nsmap={None: NS_LOTE})
    envio = etree.SubElement(root, E("envioLoteEventos"), grupo=str(grupo))
    ide = etree.SubElement(envio, E("ideEmpregador"))
    etree.SubElement(ide, E("tpInsc")).text = str(empresa.tp_insc)
    etree.SubElement(ide, E("nrInsc")).text = empresa.nr_insc_esocial
    tp_trans, nr_trans = empresa.transmissor
    trans = etree.SubElement(envio, E("ideTransmissor"))
    etree.SubElement(trans, E("tpInsc")).text = str(tp_trans)
    etree.SubElement(trans, E("nrInsc")).text = nr_trans
    evts = etree.SubElement(envio, E("eventos"))
    for id_evento, xml in eventos:
        ev = etree.SubElement(evts, E("evento"), Id=id_evento)
        ev.append(xml)
    return root


def _envelope(operacao_ns: str, operacao: str, parametro: str, conteudo: etree._Element) -> bytes:
    env = etree.Element(f"{{{SOAP_ENV}}}Envelope", nsmap={"soapenv": SOAP_ENV, "v1": operacao_ns})
    etree.SubElement(env, f"{{{SOAP_ENV}}}Header")
    body = etree.SubElement(env, f"{{{SOAP_ENV}}}Body")
    op = etree.SubElement(body, f"{{{operacao_ns}}}{operacao}")
    param = etree.SubElement(op, f"{{{operacao_ns}}}{parametro}")
    param.append(conteudo)
    return etree.tostring(env, xml_declaration=True, encoding="UTF-8")


def envelope_envio(lote: etree._Element) -> bytes:
    return _envelope(NS_WS_ENVIO, "EnviarLoteEventos", "loteEventos", lote)


def envelope_consulta(protocolo: str) -> bytes:
    root = etree.Element(f"{{{NS_CONSULTA}}}eSocial", nsmap={None: NS_CONSULTA})
    cons = etree.SubElement(root, f"{{{NS_CONSULTA}}}consultaLoteEventos")
    etree.SubElement(cons, f"{{{NS_CONSULTA}}}protocoloEnvio").text = protocolo
    return _envelope(NS_WS_CONSULTA, "ConsultarLoteEventos", "consulta", root)


# ---------------------------------------------------------------------------
# Transporte (TLS mútuo com o certificado A1)
# ---------------------------------------------------------------------------
@contextmanager
def _arquivos_pem(cert: Certificado):
    """O ``requests`` exige o certificado em arquivo; criamos temporários com permissão 600."""
    pasta = tempfile.mkdtemp(prefix="esocial-")
    caminho_cert = os.path.join(pasta, "cert.pem")
    caminho_chave = os.path.join(pasta, "key.pem")
    try:
        for caminho, conteudo in ((caminho_cert, cert.cert_pem), (caminho_chave, cert.chave_pem)):
            fd = os.open(caminho, os.O_WRONLY | os.O_CREAT, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(conteudo)
        yield caminho_cert, caminho_chave
    finally:
        for caminho in (caminho_cert, caminho_chave):
            if os.path.exists(caminho):
                os.remove(caminho)
        os.rmdir(pasta)


def _post(url: str, action: str, corpo: bytes, cert: Certificado) -> bytes:
    headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{action}"'}
    with _arquivos_pem(cert) as (c, k):
        try:
            resp = requests.post(
                url, data=corpo, headers=headers, cert=(c, k), timeout=settings.ESOCIAL_TIMEOUT,
                verify=settings.ESOCIAL_CA_BUNDLE or True,
            )
        except requests.RequestException as exc:
            raise ErroWebservice(f"Falha de comunicação com o eSocial: {exc}") from exc
    if resp.status_code >= 500 and b"Fault" not in resp.content:
        raise ErroWebservice(f"eSocial respondeu HTTP {resp.status_code}.")
    return resp.content


# ---------------------------------------------------------------------------
# Leitura das respostas (independente de namespace)
# ---------------------------------------------------------------------------
def _txt(node, caminho: str) -> str:
    achados = node.xpath(caminho)
    if not achados:
        return ""
    valor = achados[0]
    return (valor if isinstance(valor, str) else (valor.text or "")).strip()


def _ln(*partes: str) -> str:
    return "/".join(f"*[local-name()='{p}']" for p in partes)


@dataclass
class RetornoEnvio:
    cd_resposta: str
    desc_resposta: str
    protocolo: str
    ocorrencias: list[str] = field(default_factory=list)
    xml: bytes = b""

    @property
    def aceito(self) -> bool:
        return self.cd_resposta == "201"


@dataclass
class RetornoEvento:
    id_evento: str
    cd_resposta: str
    desc_resposta: str
    recibo: str
    ocorrencias: list[str]

    @property
    def sucesso(self) -> bool:
        return self.cd_resposta in {"201", "202"}


@dataclass
class RetornoConsulta:
    cd_resposta: str
    desc_resposta: str
    eventos: list[RetornoEvento]
    ocorrencias: list[str] = field(default_factory=list)
    xml: bytes = b""

    @property
    def em_processamento(self) -> bool:
        return self.cd_resposta == "101"


def _ocorrencias(node) -> list[str]:
    saida = []
    for oc in node.xpath(".//*[local-name()='ocorrencia']"):
        codigo = _txt(oc, _ln("codigo"))
        desc = _txt(oc, _ln("descricao"))
        loc = _txt(oc, _ln("localizacao"))
        saida.append(f"[{codigo}] {desc}" + (f" ({loc})" if loc else ""))
    return saida


def _fault(doc) -> str:
    return _txt(doc, ".//*[local-name()='Fault']/*[local-name()='faultstring']")


def ler_retorno_envio(xml: bytes) -> RetornoEnvio:
    doc = etree.fromstring(xml)
    if fault := _fault(doc):
        raise ErroWebservice(f"SOAP Fault: {fault}")
    ret = doc.xpath(".//*[local-name()='retornoEnvioLoteEventos']")
    if not ret:
        raise ErroWebservice("Resposta do eSocial sem retornoEnvioLoteEventos.")
    r = ret[0]
    return RetornoEnvio(
        cd_resposta=_txt(r, _ln("status", "cdResposta")),
        desc_resposta=_txt(r, _ln("status", "descResposta")),
        protocolo=_txt(r, _ln("dadosRecepcaoLote", "protocoloEnvio")),
        ocorrencias=_ocorrencias(r),
        xml=xml,
    )


def ler_retorno_consulta(xml: bytes) -> RetornoConsulta:
    doc = etree.fromstring(xml)
    if fault := _fault(doc):
        raise ErroWebservice(f"SOAP Fault: {fault}")
    ret = doc.xpath(".//*[local-name()='retornoProcessamentoLoteEventos']")
    if not ret:
        raise ErroWebservice("Resposta do eSocial sem retornoProcessamentoLoteEventos.")
    r = ret[0]
    eventos = []
    for ev in r.xpath(".//*[local-name()='retornoEventos']/*[local-name()='evento']"):
        proc = ev.xpath(".//*[local-name()='retornoEvento']//*[local-name()='processamento']")
        p = proc[0] if proc else ev
        eventos.append(
            RetornoEvento(
                id_evento=ev.get("Id", ""),
                cd_resposta=_txt(p, _ln("cdResposta")),
                desc_resposta=_txt(p, _ln("descResposta")),
                recibo=_txt(ev, ".//*[local-name()='recibo']/*[local-name()='nrRecibo']"),
                ocorrencias=_ocorrencias(p),
            )
        )
    status = r.xpath(_ln("status"))
    return RetornoConsulta(
        cd_resposta=_txt(r, _ln("status", "cdResposta")),
        desc_resposta=_txt(r, _ln("status", "descResposta")),
        eventos=eventos,
        ocorrencias=_ocorrencias(status[0]) if status else [],
        xml=xml,
    )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------
def enviar_lote(ambiente: int, lote: etree._Element, cert: Certificado) -> RetornoEnvio:
    resposta = _post(URLS[ambiente]["envio"], ACTION_ENVIO, envelope_envio(lote), cert)
    return ler_retorno_envio(resposta)


def consultar_lote(ambiente: int, protocolo: str, cert: Certificado) -> RetornoConsulta:
    resposta = _post(URLS[ambiente]["consulta"], ACTION_CONSULTA, envelope_consulta(protocolo), cert)
    return ler_retorno_consulta(resposta)
