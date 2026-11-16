"""Cadastro aberto: qualquer dona cadastra a empresa, que fica em análise até o escritório liberar."""

from unittest.mock import Mock, patch

import requests
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings

from empresas.consulta_cnpj import consultar_cnpj
from empresas.models import Acesso, Empresa
from folha.tests.fabrica import empresa
from portal.forms import TERMOS_VERSAO

CNPJ = "12.345.678/0001-95"
DA_BRASILAPI = {"razao_social": "Doces da Ana LTDA", "nome_fantasia": "Doces da Ana", "cnae": "1091102",
                "municipio": "CUIABA", "uf": "MT"}


def dados(**kw):
    d = {
        "nome": "Ana Souza", "cpf": "529.982.247-25", "email": "Ana@Exemplo.com", "celular": "(65) 99999-0000",
        "cnpj": CNPJ, "razao_social": "", "funcionarios": "2",
        "senha1": "Doces-da-Ana-2026!", "senha2": "Doces-da-Ana-2026!", "aceite": "on", "site": "",
    }
    d.update(kw)
    return d


@override_settings(CADASTRO_MAX_POR_HORA=5)
@patch("portal.forms.consultar_cnpj", return_value=DA_BRASILAPI)
class CadastroTests(TestCase):
    def setUp(self):
        cache.clear()

    def _nada_criado(self, usuarios=0, empresas=0):
        self.assertEqual(User.objects.count(), usuarios)
        self.assertEqual(Empresa.objects.count(), empresas)
        self.assertEqual(Acesso.objects.count(), 0)

    def test_cadastro_cria_dona_empresa_em_analise_e_acesso(self, _consulta):
        r = self.client.post("/cadastro/", dados())
        self.assertRedirects(r, "/cliente/", fetch_redirect_response=False)
        u = User.objects.get()
        self.assertEqual((u.username, u.email, u.first_name, u.is_staff), ("ana@exemplo.com", "ana@exemplo.com", "Ana", False))
        e = Empresa.objects.get()
        self.assertEqual((e.nr_insc, e.situacao, e.ativa), ("12345678000195", "em_analise", False))
        self.assertEqual((e.razao_social, e.cnae, e.municipio, e.uf), ("Doces da Ana LTDA", "1091102", "CUIABA", "MT"))
        self.assertEqual(e.funcionarios_informados, 2)
        a = Acesso.objects.get()
        self.assertEqual((a.usuario, a.empresa, a.termos_versao), (u, e, TERMOS_VERSAO))
        self.assertEqual((a.cpf, a.celular), ("52998224725", "(65) 99999-0000"))
        self.assertContains(self.client.get("/cliente/"), "Recebemos seu cadastro")  # já entrou logada

    def test_cnpj_ja_existe_com_ou_sem_pontuacao_da_mensagem_neutra(self, _consulta):
        existente = empresa(razao_social="Empresa Que Já Existe LTDA", nr_insc=CNPJ)
        for cnpj in (CNPJ, "12345678000195"):
            with self.subTest(cnpj=cnpj):
                r = self.client.post("/cadastro/", dados(cnpj=cnpj))
                self.assertContains(r, "Essa empresa já tem cadastro")
                self.assertNotContains(r, existente.razao_social)
        self._nada_criado(empresas=1)

    def test_email_ja_usado(self, _consulta):
        User.objects.create_user("ana@exemplo.com", email="ana@exemplo.com", password="x")
        r = self.client.post("/cadastro/", dados(email="ANA@exemplo.com"))
        self.assertContains(r, "Já existe uma conta com esse e-mail")
        self._nada_criado(usuarios=1)

    def test_cpf_e_cnpj_invalidos(self, _consulta):
        r = self.client.post("/cadastro/", dados(cpf="111.111.111-11", cnpj="11.111.111/1111-11"))
        self.assertContains(r, "CPF inválido.")
        self.assertContains(r, "CNPJ inválido.")
        self._nada_criado()

    def test_sem_aceite_nao_cadastra(self, _consulta):
        d = dados()
        del d["aceite"]
        self.assertEqual(self.client.post("/cadastro/", d).status_code, 200)
        self._nada_criado()

    def test_senha_fraca_ou_diferente_nao_cadastra(self, _consulta):
        self.client.post("/cadastro/", dados(senha1="123", senha2="123"))
        self.client.post("/cadastro/", dados(senha2="Outra-senha-2026!"))
        self._nada_criado()

    def test_armadilha_preenchida_nao_cria_nada(self, _consulta):
        self.client.post("/cadastro/", dados(site="http://spam.example"))
        self._nada_criado()

    def test_limite_por_ip(self, _consulta):
        for _ in range(5):
            self.client.post("/cadastro/", dados(cpf="111.111.111-11"))
        r = self.client.post("/cadastro/", dados())
        self.assertContains(r, "Muitas tentativas")
        self._nada_criado()

    def test_brasilapi_fora_pede_nome_da_empresa(self, consulta):
        consulta.return_value = None
        r = self.client.post("/cadastro/", dados())
        self.assertContains(r, "Digite a razão social")
        self._nada_criado()
        self.client.post("/cadastro/", dados(razao_social="Doces da Ana LTDA"))
        e = Empresa.objects.get()
        self.assertEqual((e.razao_social, e.situacao), ("Doces da Ana LTDA", "em_analise"))

    def test_logada_em_cadastro_vai_para_o_portal(self, _consulta):
        self.client.force_login(User.objects.create_user("ana@exemplo.com", password="x"))
        self.assertRedirects(self.client.get("/cadastro/"), "/cliente/", fetch_redirect_response=False)


class LoginEPaginasPublicasTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_login_com_email_em_maiusculas(self):
        User.objects.create_user("ana@exemplo.com", email="ana@exemplo.com", password="Doces-da-Ana-2026!")
        r = self.client.post("/entrar/", {"username": "ANA@Exemplo.com", "password": "Doces-da-Ana-2026!"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.session.get("_auth_user_id"), str(User.objects.get().pk))

    def test_termos_e_privacidade_abrem_sem_login(self):
        self.assertContains(self.client.get("/termos/"), "Termos de uso")
        self.assertContains(self.client.get("/privacidade/"), "Política de privacidade")

    def test_login_mostra_link_do_cadastro(self):
        self.assertContains(self.client.get("/entrar/"), 'href="/cadastro/"')


class ConsultaCnpjTests(TestCase):
    @patch("empresas.consulta_cnpj.requests.get")
    def test_mapeia_a_brasilapi_e_qualquer_falha_vira_none(self, get):
        get.return_value = Mock(status_code=200, json=lambda: {
            "razao_social": "DOCES DA ANA LTDA", "nome_fantasia": "", "cnae_fiscal": 1091102,
            "municipio": "CUIABA", "uf": "MT"})
        self.assertEqual(consultar_cnpj(CNPJ), {"razao_social": "DOCES DA ANA LTDA", "nome_fantasia": "",
                                                "cnae": "1091102", "municipio": "CUIABA", "uf": "MT"})
        self.assertIn("/12345678000195", get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs["timeout"], 5)

        get.return_value = Mock(status_code=404, json=lambda: {})
        self.assertIsNone(consultar_cnpj(CNPJ))
        get.side_effect = requests.Timeout
        self.assertIsNone(consultar_cnpj(CNPJ))
