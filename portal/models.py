from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import models

from empresas.models import Empresa, _storage_privado
from folha.models import Ferias, Rescisao
from pessoal.models import Funcionario


class Pedido(models.Model):
    """O que a dona pede ao escritório. As respostas ficam aqui até o escritório aprovar (nada vai antes ao eSocial)."""

    TIPOS = [
        ("contratei", "Contratei alguém"),
        ("sair", "Alguém vai sair"),
        ("ferias", "Férias"),
        ("alterar", "Alterar dados de alguém"),
        ("documento", "Mandar documento"),
        ("duvida", "Dúvida"),
    ]
    SITUACOES = [
        ("enviado", "Enviado"),
        ("em_analise", "Em análise"),
        ("devolvido", "Devolvido para corrigir"),
        ("aprovado", "Aprovado"),
        ("concluido", "Concluído"),
        ("cancelado", "Cancelado"),
    ]
    ABERTOS = ("enviado", "em_analise", "devolvido")

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="pedidos")
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    tipo = models.CharField(max_length=10, choices=TIPOS)
    situacao = models.CharField("situação", max_length=10, choices=SITUACOES, default="enviado")
    respostas = models.JSONField(default=dict, blank=True)
    funcionario = models.ForeignKey(Funcionario, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos")
    ferias = models.ForeignKey(Ferias, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    rescisao = models.ForeignKey(Rescisao, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Pedido {self.pk}: {self.get_tipo_display()}"

    @property
    def aberto(self):
        return self.situacao in self.ABERTOS

    def mudar(self, situacao: str, por, texto: str = "") -> None:
        self.situacao = situacao
        self.save(update_fields=["situacao", "atualizado_em"])
        if texto:
            Mensagem.objects.create(pedido=self, autor=por, texto=texto)

    def evento_aceito(self) -> bool:
        from esocial.models import Evento

        filtro = {
            "contratei": ("S-2200", "funcionario", self.funcionario_id),
            "sair": ("S-2299", "funcionario", self.funcionario_id),
            "ferias": ("S-2230", "ferias", self.ferias_id),
        }.get(self.tipo)
        if not filtro or filtro[2] is None:
            return False
        tipo, campo, valor = filtro
        return Evento.objects.filter(tipo=tipo, status="aceito", **{campo: valor}).exists()


def concluir_os_aceitos(pedidos) -> None:
    for p in pedidos.filter(situacao="aprovado"):
        if p.evento_aceito():
            p.mudar("concluido", None, "O eSocial recebeu e aceitou. Pedido concluído.")


class Mensagem(models.Model):
    """Conversa do pedido. Autor vazio = aviso do sistema (mudança de situação)."""

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="mensagens")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    texto = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["criado_em", "pk"]


def _caminho_anexo(instance, filename):
    return f"anexos/pedido_{instance.pedido_id}/{uuid4().hex}{Path(filename).suffix}"


class Anexo(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="anexos")
    arquivo = models.FileField(storage=_storage_privado, upload_to=_caminho_anexo)
    nome = models.CharField(max_length=100)
    tipo_conteudo = models.CharField(max_length=40)
    tamanho = models.PositiveIntegerField()
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["criado_em", "pk"]
