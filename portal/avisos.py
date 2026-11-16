"""Avisos por e-mail do portal: pedido novo, mensagens, mudanças de situação e cadastro de empresa.

Saem depois de gravar (on_commit), um e-mail por pessoa, e erro de envio só vai para o log: nunca derruba a tela.
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from empresas.acesso import eh_escritorio

from .models import Mensagem, Pedido

log = logging.getLogger(__name__)
User = get_user_model()


def _link(rota, *args) -> str:
    return settings.FOLHA_SITE_URL.rstrip("/") + reverse(rota, args=args)


def _escritorio() -> list[str]:
    return settings.FOLHA_ESCRITORIO_EMAIL or list(
        User.objects.filter(is_staff=True, is_active=True).exclude(email="").values_list("email", flat=True))


def _donas(empresa) -> list[str]:
    return list(User.objects.filter(acessos__empresa=empresa, is_active=True, is_staff=False)
                .exclude(email="").values_list("email", flat=True).distinct())


def _enviar(para: list[str], assunto: str, texto: str) -> None:
    def mandar():
        for email in para:
            try:
                send_mail(assunto, texto, None, [email])
            except Exception:  # SMTP fora do ar ou mal configurado
                log.exception("Aviso por e-mail não saiu: %s", assunto)

    if para:
        transaction.on_commit(mandar)


@receiver(post_save, sender=Pedido)
def pedido_novo(sender, instance, created, **kwargs):
    if created:
        p = instance
        _enviar(_escritorio(), f"Pedido novo: {p.get_tipo_display()} ({p.empresa.razao_social})",
                f"{p.empresa.razao_social} mandou um pedido: {p.get_tipo_display()}.\n\n"
                f"Abra para conferir: {_link('portal:escritorio_pedido', p.pk)}")


@receiver(post_save, sender=Mensagem)
def mensagem_nova(sender, instance, created, **kwargs):
    if not created:
        return
    p = instance.pedido
    if instance.autor and not eh_escritorio(instance.autor):  # a dona escreveu: avisa o escritório
        _enviar(_escritorio(), f"Mensagem da cliente no pedido nº {p.pk} ({p.empresa.razao_social})",
                f"{instance.texto}\n\nResponda em: {_link('portal:escritorio_pedido', p.pk)}")
    else:  # o escritório escreveu ou a situação mudou: avisa a dona
        _enviar(_donas(p.empresa), f"Novidade no seu pedido: {p.get_tipo_display()}",
                f"{instance.texto}\n\nVeja no portal: {_link('portal:pedido', p.pk)}")


def cadastro_novo(empresa) -> None:
    _enviar(_escritorio(), f"Nova empresa para conferir: {empresa.razao_social}",
            f"{empresa.razao_social} se cadastrou no portal.\n\nConfira e libere: {_link('empresas:validar', empresa.pk)}")
