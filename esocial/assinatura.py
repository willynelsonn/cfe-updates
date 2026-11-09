"""Assinatura digital XMLDSig dos eventos (certificado A1, RSA-SHA256, C14N inclusiva)."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree

DS = "http://www.w3.org/2000/09/xmldsig#"
C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"


class ErroCertificado(Exception):
    pass


@dataclass
class Certificado:
    chave_pem: bytes
    cert_pem: bytes
    titular: str
    validade: datetime

    @property
    def vencido(self) -> bool:
        return self.validade < datetime.now(timezone.utc)


def carregar_pfx(conteudo: bytes, senha: str) -> Certificado:
    try:
        chave, cert, _ = pkcs12.load_key_and_certificates(conteudo, senha.encode() if senha else None)
    except ValueError as exc:
        raise ErroCertificado("Não foi possível abrir o certificado: senha incorreta ou arquivo inválido.") from exc
    if chave is None or cert is None:
        raise ErroCertificado("O arquivo .pfx não contém chave privada e certificado.")
    chave_pem = chave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    titular = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
    return Certificado(
        chave_pem=chave_pem,
        cert_pem=cert_pem,
        titular=titular[0].value if titular else cert.subject.rfc4514_string(),
        validade=cert.not_valid_after_utc,
    )


def _c14n(el: etree._Element) -> bytes:
    """Canonicalização C14N 1.0 inclusiva, sem comentários.

    O elemento é copiado para um documento próprio antes de canonicalizar: algumas
    versões do libxml2 (ex.: 2.14) geram ``xmlns=""`` indevido ao canonicalizar uma
    subárvore cujo namespace padrão é herdado (caso do <SignedInfo>), o que tornaria
    a assinatura inválida para o eSocial. Nossos XMLs só usam namespace padrão, então
    a cópia isolada produz exatamente a forma canônica correta.
    """
    isolado = etree.fromstring(etree.tostring(el))
    return etree.tostring(isolado, method="c14n", exclusive=False, with_comments=False)


def assinar(root: etree._Element, certificado: Certificado) -> etree._Element:
    """Assinatura XMLDSig envelopada do documento inteiro, no padrão do eSocial.

    - Reference URI="" com transforms enveloped-signature + C14N
    - Digest SHA-256, assinatura RSA-SHA256
    - Elemento <Signature> sem prefixo, como último filho da raiz <eSocial>
    """
    if certificado.vencido:
        raise ErroCertificado(f"Certificado vencido em {certificado.validade:%d/%m/%Y}.")

    doc = etree.fromstring(etree.tostring(root))
    for antiga in doc.findall(f"{{{DS}}}Signature"):
        doc.remove(antiga)

    # Transform enveloped-signature + C14N sobre o documento sem a assinatura
    digest = base64.b64encode(hashlib.sha256(_c14n(doc)).digest()).decode()

    def ds(parent, tag, **attrs):
        return etree.SubElement(parent, f"{{{DS}}}{tag}", **attrs)

    assinatura = etree.SubElement(doc, f"{{{DS}}}Signature", nsmap={None: DS})
    signed_info = ds(assinatura, "SignedInfo")
    ds(signed_info, "CanonicalizationMethod", Algorithm=C14N)
    ds(signed_info, "SignatureMethod", Algorithm=RSA_SHA256)
    ref = ds(signed_info, "Reference", URI="")
    transforms = ds(ref, "Transforms")
    ds(transforms, "Transform", Algorithm=ENVELOPED)
    ds(transforms, "Transform", Algorithm=C14N)
    ds(ref, "DigestMethod", Algorithm=SHA256)
    ds(ref, "DigestValue").text = digest

    chave = serialization.load_pem_private_key(certificado.chave_pem, password=None)
    valor = chave.sign(_c14n(signed_info), padding.PKCS1v15(), hashes.SHA256())
    ds(assinatura, "SignatureValue").text = base64.b64encode(valor).decode()

    cert_der = x509.load_pem_x509_certificate(certificado.cert_pem).public_bytes(serialization.Encoding.DER)
    x509_data = ds(ds(assinatura, "KeyInfo"), "X509Data")
    ds(x509_data, "X509Certificate").text = base64.b64encode(cert_der).decode()
    return doc
