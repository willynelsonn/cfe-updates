"""Anexos dos pedidos: só foto (JPG/PNG) ou PDF, até 5 MB, conferidos pelos primeiros bytes (não pelo nome)."""

from pathlib import Path

from django.core.exceptions import ValidationError

MAX_BYTES = 5 * 1024 * 1024
ASSINATURAS = {b"%PDF-": "application/pdf", b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg"}
EXTENSOES = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}


def tipo_do_arquivo(arquivo) -> str:
    if arquivo.size > MAX_BYTES:
        raise ValidationError("O arquivo passa de 5 MB. Tire a foto de novo ou mande um PDF menor.")
    arquivo.seek(0)
    inicio = arquivo.read(8)
    arquivo.seek(0)
    for assinatura, tipo in ASSINATURAS.items():
        if inicio.startswith(assinatura):
            return tipo
    raise ValidationError("Envie foto (JPG ou PNG) ou PDF.")


def anexar(pedido, arquivo, por):
    from .models import Anexo

    tipo = tipo_do_arquivo(arquivo)
    a = Anexo(pedido=pedido, nome=Path(arquivo.name).name[:100], tipo_conteudo=tipo, tamanho=arquivo.size,
              enviado_por=por)
    a.arquivo.save("anexo" + EXTENSOES[tipo], arquivo)  # o caminho real vem de _caminho_anexo (sem o nome enviado)
    return a
