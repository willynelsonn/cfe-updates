"""Convite: link de uso único (7 dias) para a dona de uma empresa que o escritório já atende."""

import hashlib
import re
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from empresas.models import Acesso, Convite

from .fabrica import dona, duas_empresas

NOVA = {"nome": "Bia Lima", "cpf": "529.982.247-25", "email": "Bia@Exemplo.com",
        "senha1": "Bolos-da-Bia-2026!", "senha2": "Bolos-da-Bia-2026!", "aceite": "on"}


class ConviteTests(TestCase):
    def setUp(self):
        self.a, self.b = duas_empresas()
        self.staff = User.objects.create_user("escritorio", password="x", is_staff=True)

    def _convite(self, empresa=None):
        _, codigo = Convite.criar(empresa or self.b, self.staff)
        return f"/convite/{codigo}/"

    def test_convite_cria_conta_e_vinculo_uma_vez(self):
        url = self._convite()
        self.assertContains(self.client.get(url), self.b.razao_social)
        self.assertRedirects(self.client.post(url, NOVA), "/cliente/", fetch_redirect_response=False)
        u = User.objects.get(username="bia@exemplo.com")
        self.assertFalse(u.is_staff)
        self.assertEqual(list(Acesso.objects.filter(usuario=u).values_list("empresa", flat=True)), [self.b.pk])
        c = Convite.objects.get()
        self.assertEqual(c.usado_por, u)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, dict(NOVA, email="outra@exemplo.com")).status_code, 404)

    def test_convite_vencido_404(self):
        url = self._convite()
        Convite.objects.update(criado_em=timezone.now() - timedelta(days=8))
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get("/convite/codigo-inventado/").status_code, 404)

    def test_dona_logada_aceita_convite_de_outra_empresa(self):
        dona_a = dona(self.a)
        url = self._convite(self.b)
        self.client.force_login(dona_a)
        r = self.client.get(url)
        self.assertContains(r, "Vincular")
        self.assertNotContains(r, 'name="senha1"')
        self.assertRedirects(self.client.post(url), "/cliente/", fetch_redirect_response=False)
        self.assertEqual(set(Acesso.objects.filter(usuario=dona_a).values_list("empresa", flat=True)), {self.a.pk, self.b.pk})
        self.assertIsNotNone(Convite.objects.get().usado_em)

    def test_escritorio_abrindo_o_link_nao_gasta_o_convite(self):
        url = self._convite()
        self.client.force_login(self.staff)
        self.client.post(url)
        self.assertIsNone(Convite.objects.get().usado_em)

    def test_so_escritorio_gera_convite(self):
        url = f"/empresas/{self.b.pk}/convidar/"
        self.client.force_login(dona(self.a))
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(Convite.objects.count(), 0)

    def test_link_mostrado_uma_vez_e_banco_guarda_so_hash(self):
        self.client.force_login(self.staff)
        r = self.client.post(f"/empresas/{self.b.pk}/convidar/")
        codigo = re.search(r"/convite/([A-Za-z0-9_-]{20,})/", r.content.decode()).group(1)
        self.assertContains(r, "https://wa.me/?text=")
        c = Convite.objects.get()
        self.assertEqual((c.empresa, c.criado_por), (self.b, self.staff))
        self.assertEqual(c.codigo_hash, hashlib.sha256(codigo.encode()).hexdigest())
        self.assertNotIn(codigo, c.codigo_hash)
        self.assertNotContains(self.client.get("/empresas/"), codigo)

    def test_lista_tem_botao_convidar(self):
        self.client.force_login(self.staff)
        self.assertContains(self.client.get("/empresas/"), f'action="/empresas/{self.b.pk}/convidar/"')
