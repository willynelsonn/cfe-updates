"""Quem não é do escritório só enxerga o portal e a própria empresa."""

from django.contrib.auth.models import AnonymousUser, User
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from empresas.middleware import EmpresaAtivaMiddleware

from .fabrica import dona, duas_empresas


class BloqueioPorPadraoTests(TestCase):
    def setUp(self):
        self.a, self.b = duas_empresas()
        self.dona_a = dona(self.a)
        self.staff = User.objects.create_user("escritorio", password="x", is_staff=True)

    def test_cliente_get_em_rota_do_escritorio_vai_para_portal(self):
        self.client.force_login(self.dona_a)
        for rota in ("/", "/folha/", "/empresas/", "/funcionarios/", "/esocial/", "/admin/"):
            with self.subTest(rota=rota):
                self.assertRedirects(self.client.get(rota), "/cliente/", fetch_redirect_response=False)

    def test_cliente_post_em_rota_do_escritorio_e_403(self):
        self.client.force_login(self.dona_a)
        self.assertEqual(self.client.post("/empresas/nova/", {"razao_social": "X"}).status_code, 403)
        self.assertEqual(self.client.post(f"/empresas/{self.b.pk}/selecionar/").status_code, 403)

    def test_cliente_usa_rotas_da_conta(self):
        self.client.force_login(self.dona_a)
        self.assertEqual(self.client.get("/conta/senha/").status_code, 200)

    def test_escritorio_continua_igual(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/folha/").status_code, 200)

    def test_anonimo_continua_indo_para_login(self):
        self.assertRedirects(self.client.get("/folha/"), "/entrar/?next=/folha/", fetch_redirect_response=False)


class EmpresaDaClienteTests(TestCase):
    def setUp(self):
        self.a, self.b = duas_empresas()

    def _empresa_vista(self, user, empresa_id=None):
        req = RequestFactory().get("/cliente/")
        req.user = user
        req.session = SessionStore()
        if empresa_id:
            req.session["empresa_id"] = empresa_id
        return EmpresaAtivaMiddleware(lambda r: r.empresa)(req)

    def test_sessao_com_outra_empresa_nao_vaza(self):
        self.assertEqual(self._empresa_vista(dona(self.a), empresa_id=self.b.pk), self.a)

    def test_cliente_sem_vinculo_fica_sem_empresa(self):
        sem_vinculo = User.objects.create_user("sem@exemplo.com")
        self.assertIsNone(self._empresa_vista(sem_vinculo))
        self.assertIsNone(self._empresa_vista(sem_vinculo, empresa_id=self.a.pk))

    def test_dona_ve_a_empresa_mesmo_em_analise(self):
        self.a.situacao, self.a.ativa = "em_analise", False
        self.a.save()
        self.assertEqual(self._empresa_vista(dona(self.a)), self.a)

    def test_escritorio_escolhe_qualquer_empresa_ativa(self):
        staff = User.objects.create_user("escritorio", is_staff=True)
        self.assertEqual(self._empresa_vista(staff, empresa_id=self.b.pk), self.b)
        self.assertIsNone(self._empresa_vista(AnonymousUser()))
