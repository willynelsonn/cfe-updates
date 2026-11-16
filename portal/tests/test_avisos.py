"""Avisos por e-mail: saem depois de gravar, só para quem precisa saber, e falha de envio não derruba a tela."""

from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase

from portal.models import Pedido

from .fabrica import dona, duas_empresas
from .test_cadastro import DA_BRASILAPI, dados


class AvisosTests(TestCase):
    def setUp(self):
        self.a, self.b = duas_empresas()
        self.dona_a = dona(self.a)
        self.dona_b = dona(self.b, email="outra@exemplo.com")
        self.escritorio = User.objects.create_user("escritorio", email="escritorio@exemplo.com", password="x",
                                                   is_staff=True)

    def enviar(self, url, dados):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(url, dados)

    def test_pedido_novo_avisa_o_escritorio(self):
        self.client.force_login(self.dona_a)
        self.enviar("/cliente/pedidos/novo/duvida/", {"texto": "Pergunta inventada"})
        [m] = mail.outbox
        p = Pedido.objects.get()
        self.assertEqual(m.to, ["escritorio@exemplo.com"])
        self.assertIn(f"/pedidos/{p.pk}/", m.body)

    def test_devolver_avisa_so_a_dona_da_empresa(self):
        p = Pedido.objects.create(empresa=self.a, criado_por=self.dona_a, tipo="duvida", respostas={"texto": "x"})
        self.client.force_login(self.escritorio)
        self.enviar(f"/pedidos/{p.pk}/", {"acao": "devolver", "texto": "Falta o CPF da pessoa"})
        [m] = mail.outbox
        self.assertEqual(m.to, ["dona@exemplo.com"])
        self.assertIn("Falta o CPF da pessoa", m.body)
        self.assertIn(f"/cliente/pedidos/{p.pk}/", m.body)

    def test_mensagem_da_dona_vai_so_ao_escritorio(self):
        p = Pedido.objects.create(empresa=self.a, criado_por=self.dona_a, tipo="duvida", respostas={"texto": "x"})
        self.client.force_login(self.dona_a)
        self.enviar(f"/cliente/pedidos/{p.pk}/", {"texto": "Mais uma coisa"})
        self.assertEqual([m.to for m in mail.outbox], [["escritorio@exemplo.com"]])

    def test_erro_no_envio_nao_derruba_a_tela(self):
        self.client.force_login(self.dona_a)
        with mock.patch("portal.avisos.send_mail", side_effect=OSError("SMTP fora do ar")):
            r = self.enviar("/cliente/pedidos/novo/duvida/", {"texto": "Pergunta inventada"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Pedido.objects.exists())

    @mock.patch("portal.forms.consultar_cnpj", return_value=DA_BRASILAPI)
    def test_cadastro_novo_avisa_o_escritorio(self, _):
        r = self.enviar("/cadastro/", dados())
        self.assertEqual(r.status_code, 302)
        [m] = mail.outbox
        self.assertEqual(m.to, ["escritorio@exemplo.com"])
        self.assertIn("/validar/", m.body)

    def test_dona_que_cancela_nao_recebe_aviso_do_proprio_cancelamento(self):
        p = Pedido.objects.create(empresa=self.a, criado_por=self.dona_a, tipo="duvida", respostas={"texto": "x"})
        self.client.force_login(self.dona_a)
        self.enviar(f"/cliente/pedidos/{p.pk}/cancelar/", {})
        self.assertEqual([m.to for m in mail.outbox], [["escritorio@exemplo.com"]])
