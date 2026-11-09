from django.db import models

from empresas.models import Empresa
from folha.models import Competencia, Ferias
from pessoal.models import Funcionario


class Lote(models.Model):
    STATUS = [
        ("enviado", "Enviado - aguardando processamento"),
        ("processado", "Processado"),
        ("rejeitado", "Rejeitado na recepção"),
        ("erro", "Erro de comunicação"),
    ]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="lotes_esocial")
    grupo = models.PositiveSmallIntegerField()
    ambiente = models.PositiveSmallIntegerField()
    protocolo = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="enviado")
    cd_resposta = models.CharField(max_length=5, blank=True)
    desc_resposta = models.TextField(blank=True)
    xml_envio = models.TextField(blank=True)
    xml_retorno_envio = models.TextField(blank=True)
    xml_retorno_consulta = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    consultado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Lote {self.protocolo or self.pk} (grupo {self.grupo})"


class Evento(models.Model):
    STATUS = [
        ("pendente", "Na fila de envio"),
        ("enviado", "Enviado"),
        ("aceito", "Aceito"),
        ("rejeitado", "Rejeitado"),
        ("erro", "Erro"),
    ]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="eventos_esocial")
    tipo = models.CharField(max_length=6)  # S-1000, S-2200...
    descricao = models.CharField(max_length=200)
    chave = models.CharField(
        max_length=80, db_index=True, blank=True,
        help_text="Identifica o objeto do evento (ex.: S-2200:func:5) para dependências e reenvio.",
    )
    depende = models.JSONField(
        default=list, blank=True, help_text="Chaves de eventos que precisam estar aceitos antes do envio."
    )
    id_evento = models.CharField(max_length=36, unique=True)
    funcionario = models.ForeignKey(Funcionario, on_delete=models.SET_NULL, null=True, blank=True)
    competencia = models.ForeignKey(Competencia, on_delete=models.SET_NULL, null=True, blank=True)
    ferias = models.ForeignKey(Ferias, on_delete=models.SET_NULL, null=True, blank=True)
    per_apur = models.CharField(max_length=7, blank=True)
    xml = models.TextField()
    xml_assinado = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="pendente")
    lote = models.ForeignKey(Lote, on_delete=models.SET_NULL, null=True, blank=True, related_name="eventos")
    recibo = models.CharField(max_length=40, blank=True)
    mensagens = models.JSONField(default=list, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.tipo} - {self.descricao}"

    @property
    def corrigivel(self):
        return self.status in {"rejeitado", "erro"}

    @property
    def grupo(self):
        from .xml_eventos import EVENTOS

        return EVENTOS[self.tipo][1]
