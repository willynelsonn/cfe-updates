"""A página /cliente/ mostra à dona em que pé está o cadastro da empresa."""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from folha.tests.fabrica import empresa

from .fabrica import dona


@override_settings(FOLHA_ESCRITORIO_CNPJ="11444777000161", FOLHA_ESCRITORIO_NOME="Escritório Teste")
class InicioTests(TestCase):
    def _abrir(self, **kw):
        self.client.force_login(dona(empresa(**kw)))
        return self.client.get("/cliente/")

    def test_em_analise_mostra_passo_a_passo_da_procuracao(self):
        r = self._abrir(situacao="em_analise", ativa=False)
        self.assertContains(r, "Recebemos seu cadastro")
        self.assertContains(r, "11.444.777/0001-61")
        self.assertContains(r, "Escritório Teste")

    def test_recusada_mostra_o_motivo(self):
        r = self._abrir(situacao="recusada", ativa=False, motivo_recusa="O CNPJ não está no nome da dona.")
        self.assertContains(r, "O CNPJ não está no nome da dona.")

    def test_ativa_mostra_tudo_certo(self):
        r = self._abrir(razao_social="Doces da Ana LTDA")
        self.assertContains(r, "Tudo certo")
        self.assertContains(r, "Doces da Ana LTDA")

    def test_escritorio_vai_para_o_painel(self):
        self.client.force_login(User.objects.create_user("escritorio", password="x", is_staff=True))
        self.assertRedirects(self.client.get("/cliente/"), "/", fetch_redirect_response=False)

    def test_anonimo_vai_para_o_login(self):
        self.assertRedirects(self.client.get("/cliente/"), "/entrar/?next=/cliente/", fetch_redirect_response=False)
