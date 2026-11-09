"""Processa a fila do eSocial de todas as empresas com envio automático.

Agende no servidor (ex.: cron a cada 5 minutos):
    */5 * * * * cd /caminho/do/folhaweb && python manage.py processar_esocial
"""

from django.core.management.base import BaseCommand

from empresas.models import Empresa
from esocial.assinatura import ErroCertificado
from esocial.servico import ErroESocial, processar_fila
from folha.guias import atualizar_guias
from folha.models import Competencia


class Command(BaseCommand):
    help = "Consulta retornos e envia os eventos liberados do eSocial; atualiza as guias."

    def handle(self, *args, **opts):
        for empresa in Empresa.objects.filter(ativa=True, envio_automatico=True):
            if not empresa.tem_certificado:
                continue
            try:
                r = processar_fila(empresa)
            except (ErroESocial, ErroCertificado) as exc:
                self.stderr.write(f"{empresa}: {exc}")
                continue
            for comp in Competencia.objects.filter(empresa=empresa, status="fechada")[:3]:
                atualizar_guias(comp)
            self.stdout.write(f"{empresa}: {r}")
