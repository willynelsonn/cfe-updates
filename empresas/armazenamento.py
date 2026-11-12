"""Armazenamento de arquivos privados (certificados A1) dentro do próprio banco de dados.

Usado na nuvem (Render + Supabase), onde o disco do servidor é apagado a cada atualização.
Ative com FOLHA_ARQUIVOS_NO_BANCO=true (ligado automaticamente quando FOLHA_DATABASE_URL existe).
"""

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class BancoStorage(Storage):
    def _modelo(self):
        from .models import ArquivoPrivado

        return ArquivoPrivado

    def _open(self, name, mode="rb"):
        arq = self._modelo().objects.filter(nome=name).first()
        if arq is None:
            raise FileNotFoundError(name)
        return ContentFile(bytes(arq.conteudo), name=name)

    def _save(self, name, content):
        content.seek(0) if hasattr(content, "seek") else None
        dados = content.read()
        self._modelo().objects.update_or_create(nome=name, defaults={"conteudo": dados})
        return name

    def exists(self, name):
        return self._modelo().objects.filter(nome=name).exists()

    def delete(self, name):
        self._modelo().objects.filter(nome=name).delete()

    def size(self, name):
        arq = self._modelo().objects.filter(nome=name).first()
        return len(arq.conteudo) if arq else 0

    def listdir(self, path):
        prefixo = f"{path.rstrip('/')}/" if path else ""
        nomes = self._modelo().objects.filter(nome__startswith=prefixo).values_list("nome", flat=True)
        return [], [n[len(prefixo):] for n in nomes if "/" not in n[len(prefixo):]]

    def url(self, name):
        raise NotImplementedError("Arquivos privados não têm endereço público.")
