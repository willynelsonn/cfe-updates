"""O escritório confere a empresa que a dona cadastrou e libera ou recusa (com motivo)."""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from empresas.models import Empresa
from folha.models import Rubrica

from .fabrica import dona


def em_analise():
    return Empresa.objects.create(razao_social="Doces da Ana LTDA", nr_insc="12.345.678/0001-95", cnae="",
                                  situacao="em_analise", ativa=False, envio_automatico=False, funcionarios_informados=2)


def tecnicos(**kw):
    d = {"razao_social": "Doces da Ana LTDA", "tp_insc": "1", "nr_insc": "12.345.678/0001-95", "class_trib": "99",
         "cnae": "1091102", "fpas": "515", "cod_terceiros": "0115", "aliq_terceiros": "5.80", "aliq_rat": "1",
         "fap": "1.0000", "inicio_esocial": "2026-01", "dia_pagamento": "5", "ambiente_esocial": "2",
         "transmissor_cnpj": "", "envio_automatico": "on"}
    d.update(kw)
    return d


@override_settings(FOLHA_ESCRITORIO_CNPJ="11.444.777/0001-61")
class ValidacaoTests(TestCase):
    def setUp(self):
        self.emp = em_analise()
        self.dona = dona(self.emp)
        self.staff = User.objects.create_user("escritorio", password="x", is_staff=True)
        self.url = f"/empresas/{self.emp.pk}/validar/"

    def test_liberar_ativa_e_cria_rubricas(self):
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(self.url), "dona@exemplo.com")  # mostra quem cadastrou
        r = self.client.post(self.url, tecnicos(acao="liberar"))
        self.assertRedirects(r, "/empresas/", fetch_redirect_response=False)
        e = Empresa.objects.get(pk=self.emp.pk)
        self.assertEqual((e.situacao, e.ativa, e.envio_automatico), ("ativa", True, False))
        self.assertEqual((e.transmissor_cnpj, e.cnae), ("11444777000161", "1091102"))
        self.assertEqual(e.validada_por, self.staff)
        self.assertIsNotNone(e.validada_em)
        self.assertTrue(Rubrica.objects.filter(empresa=e).exists())

    def test_liberar_com_dado_tecnico_errado_continua_em_analise(self):
        self.client.force_login(self.staff)
        r = self.client.post(self.url, tecnicos(acao="liberar", cnae=""))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Empresa.objects.get(pk=self.emp.pk).situacao, "em_analise")

    def test_recusar_exige_motivo(self):
        self.client.force_login(self.staff)
        r = self.client.post(self.url, {"acao": "recusar", "motivo": "  "})
        self.assertContains(r, "Escreva o motivo")
        self.assertEqual(Empresa.objects.get(pk=self.emp.pk).situacao, "em_analise")
        self.client.post(self.url, {"acao": "recusar", "motivo": "O CNPJ não está no nome da dona."})
        e = Empresa.objects.get(pk=self.emp.pk)
        self.assertEqual((e.situacao, e.ativa, e.motivo_recusa), ("recusada", False, "O CNPJ não está no nome da dona."))
        self.assertEqual(e.validada_por, self.staff)

    def test_cliente_nao_valida(self):
        self.client.force_login(self.dona)
        self.assertEqual(self.client.post(self.url, tecnicos(acao="liberar")).status_code, 403)
        self.assertEqual(Empresa.objects.get(pk=self.emp.pk).situacao, "em_analise")

    def test_lista_mostra_conferir(self):
        self.client.force_login(self.staff)
        r = self.client.get("/empresas/")
        self.assertContains(r, "Em análise")
        self.assertContains(r, f'href="{self.url}"')

    def test_painel_avisa_empresas_para_conferir(self):
        self.client.force_login(self.staff)
        self.assertContains(self.client.get("/"), "1 empresa nova para conferir")
