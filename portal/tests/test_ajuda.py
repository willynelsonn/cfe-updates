"""Ajuda "O que é?": dicionário único de termos, mostrado sozinho em todo formulário que tem palavra técnica."""

from django.contrib.auth.models import User
from django.test import TestCase

from folha.tests.fabrica import funcionario
from portal.ajuda import CAMPOS, TERMOS, termo_do_campo

from .fabrica import dona, duas_empresas


class AjudaTests(TestCase):
    def test_todo_campo_aponta_para_um_termo_completo(self):
        for campo, chave in CAMPOS.items():
            self.assertIn(chave, TERMOS, campo)
        for chave, t in TERMOS.items():
            self.assertTrue(all(t.get(k) for k in ("titulo", "o_que_e", "como_preencher", "por_que")), chave)
        self.assertIsNone(termo_do_campo("nome"))

    def test_tela_da_empresa_do_escritorio_explica_o_fpas(self):
        a, _ = duas_empresas()
        self.client.force_login(User.objects.create_user("escritorio", password="x", is_staff=True))
        r = self.client.get(f"/empresas/{a.pk}/editar/")
        self.assertContains(r, "O que é?")
        self.assertContains(r, TERMOS["fpas"]["o_que_e"])

    def test_pedido_da_dona_explica_o_aviso_previo(self):
        a, _ = duas_empresas()
        funcionario(a)
        self.client.force_login(dona(a))
        self.assertContains(self.client.get("/cliente/pedidos/novo/sair/"), TERMOS["aviso_previo"]["o_que_e"])
