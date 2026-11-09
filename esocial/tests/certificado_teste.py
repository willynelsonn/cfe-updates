"""Certificado A1 autoassinado e verificador de assinatura, apenas para testes."""

import base64
import hashlib
import re
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12


def gerar_pfx(senha: str = "1234", dias: int = 365) -> bytes:
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "EMPRESA TESTE:11222333000181")])
    agora = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - timedelta(days=abs(dias) + 10))
        .not_valid_after(agora + timedelta(days=dias))
        .sign(chave, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        b"teste", chave, cert, None, serialization.BestAvailableEncryption(senha.encode())
    )


DS = "{http://www.w3.org/2000/09/xmldsig#}"


def verificar_assinatura(xml: bytes) -> None:
    """Verificador independente do lxml: usa o canonicalizador da biblioteca padrão.

    Confere o DigestValue (documento sem a assinatura) e o SignatureValue (SignedInfo)
    com a chave pública do certificado embutido em KeyInfo. Trabalha sobre o texto
    para não depender da forma como alguma biblioteca reescreve namespaces.
    """
    texto = xml.decode() if isinstance(xml, bytes) else xml
    texto = re.sub(r"^<\?xml[^>]*\?>", "", texto).strip()
    m = re.search(r"<Signature xmlns=\"http://www.w3.org/2000/09/xmldsig#\">.*</Signature>", texto, re.S)
    assert m, "sem <Signature> sem prefixo"
    assinatura_txt = m.group(0)
    sem_assinatura = ET.canonicalize(texto.replace(assinatura_txt, "")).encode()
    digest = base64.b64encode(hashlib.sha256(sem_assinatura).digest()).decode()

    assinatura = ET.fromstring(assinatura_txt)
    assert digest == assinatura.find(f"{DS}SignedInfo/{DS}Reference/{DS}DigestValue").text, "digest divergente"

    si_txt = re.search(r"<SignedInfo>.*</SignedInfo>", assinatura_txt, re.S).group(0)
    si_txt = si_txt.replace("<SignedInfo>", '<SignedInfo xmlns="http://www.w3.org/2000/09/xmldsig#">', 1)
    signed_info = ET.canonicalize(si_txt).encode()
    valor = base64.b64decode(assinatura.find(f"{DS}SignatureValue").text)
    cert = x509.load_der_x509_certificate(
        base64.b64decode(assinatura.find(f"{DS}KeyInfo/{DS}X509Data/{DS}X509Certificate").text)
    )
    cert.public_key().verify(valor, signed_info, padding.PKCS1v15(), hashes.SHA256())
