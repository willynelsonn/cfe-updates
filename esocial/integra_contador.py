"""Cliente do Integra Contador (SERPRO/Receita Federal) para emitir o DARF da DCTFWeb.

É um serviço PAGO, contratado na Loja SERPRO pelo escritório (contratante). Configure:
    FOLHA_INTEGRA_KEY / FOLHA_INTEGRA_SECRET   - consumer key/secret da Loja SERPRO
    FOLHA_INTEGRA_CONTRATANTE                  - CNPJ de quem contratou (o escritório)
O certificado e-CNPJ do contratante é usado na autenticação (TLS mútuo) e o cliente
precisa ter dado procuração eletrônica no e-CAC ao contratante.

Serviço usado: idSistema DCTFWEB / idServico GERARGUIA31 ("Gerar Guia Declaração").
Confira o catálogo atual em https://apicenter.estaleiro.serpro.gov.br (os nomes podem mudar);
o idServico é configurável por FOLHA_INTEGRA_SERVICO_DARF.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass

import requests
from django.conf import settings

from .assinatura import Certificado
from .webservice import _arquivos_pem


class ErroIntegraContador(Exception):
    pass


@dataclass
class Guia:
    pdf: bytes
    mensagens: list[str]


def configurado() -> bool:
    return bool(settings.INTEGRA_CONTADOR["key"] and settings.INTEGRA_CONTADOR["secret"]
                and settings.INTEGRA_CONTADOR["contratante"])


def _autenticar(cert: Certificado) -> tuple[str, str]:
    cfg = settings.INTEGRA_CONTADOR
    basic = base64.b64encode(f"{cfg['key']}:{cfg['secret']}".encode()).decode()
    with _arquivos_pem(cert) as (c, k):
        try:
            resp = requests.post(
                cfg["url_autenticacao"], data={"grant_type": "client_credentials"},
                headers={"Authorization": f"Basic {basic}", "Role-Type": "TERCEIROS",
                         "Content-Type": "application/x-www-form-urlencoded"},
                cert=(c, k), timeout=settings.ESOCIAL_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise ErroIntegraContador(f"Falha ao autenticar no SERPRO: {exc}") from exc
    if resp.status_code != 200:
        raise ErroIntegraContador(f"Autenticação SERPRO recusada (HTTP {resp.status_code}).")
    dados = resp.json()
    return dados["access_token"], dados["jwt_token"]


def emitir_darf_dctfweb(empresa, ano: int, mes: int, decimo_terceiro: bool, cert: Certificado) -> Guia:
    if not configurado():
        raise ErroIntegraContador("Integra Contador não configurado (veja .env.example).")
    cfg = settings.INTEGRA_CONTADOR
    access, jwt = _autenticar(cert)
    dados = {"categoria": "GERAL_13o_SALARIO" if decimo_terceiro else "GERAL_MENSAL", "anoPA": str(ano)}
    if not decimo_terceiro:
        dados["mesPA"] = f"{mes:02d}"
    corpo = {
        "contratante": {"numero": cfg["contratante"], "tipo": 2},
        "autorPedidoDados": {"numero": cfg["contratante"], "tipo": 2},
        "contribuinte": {"numero": empresa.nr_insc, "tipo": 2 if empresa.tp_insc == 1 else 1},
        "pedidoDados": {
            "idSistema": "DCTFWEB", "idServico": cfg["servico_darf"], "versaoSistema": "1.0",
            "dados": json.dumps(dados),
        },
    }
    try:
        resp = requests.post(
            cfg["url_api"].rstrip("/") + "/Emitir", json=corpo,
            headers={"Authorization": f"Bearer {access}", "jwt_token": jwt}, timeout=settings.ESOCIAL_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise ErroIntegraContador(f"Falha de comunicação com o SERPRO: {exc}") from exc
    try:
        ret = resp.json()
    except ValueError as exc:
        raise ErroIntegraContador(f"Resposta inválida do SERPRO (HTTP {resp.status_code}).") from exc
    mensagens = [f"{m.get('codigo', '')} {m.get('texto', '')}".strip() for m in ret.get("mensagens", [])]
    if resp.status_code != 200 or not ret.get("dados"):
        raise ErroIntegraContador("; ".join(mensagens) or f"SERPRO respondeu HTTP {resp.status_code}.")
    conteudo = json.loads(ret["dados"]) if isinstance(ret["dados"], str) else ret["dados"]
    pdf_b64 = conteudo.get("PDFByteArrayBase64") or conteudo.get("pdf")
    if not pdf_b64:
        raise ErroIntegraContador("O SERPRO não devolveu o PDF do DARF. " + "; ".join(mensagens))
    return Guia(pdf=base64.b64decode(pdf_b64), mensagens=mensagens)
