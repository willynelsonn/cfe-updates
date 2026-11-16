"""Fila de pedidos do escritório: conferir, conversar, devolver, cancelar, concluir e abrir o formulário técnico."""

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from empresas.models import Empresa
from folha.tests.fabrica import funcionario
from portal.anexos import anexar
from portal.models import Pedido

from .fabrica import dona, duas_empresas, usar_banco_nos_anexos

PDF = b"%PDF-1.4 teste"


class FilaEscritorioTests(TestCase):
    def setUp(self):
        usar_banco_nos_anexos(self)
        self.a, self.b = duas_empresas()
        self.dona = dona(self.a)
        self.maria = funcionario(self.a)
        self.staff = User.objects.create_user("escritorio", password="x", is_staff=True)
        self.p = Pedido.objects.create(empresa=self.a, criado_por=self.dona, tipo="contratei",
                                       respostas={"nome": "Ana Teste", "data_inicio": "2026-12-01"})
        self.url = f"/pedidos/{self.p.pk}/"
        self.client.force_login(self.staff)

    def situacao(self, p=None):
        return Pedido.objects.get(pk=(p or self.p).pk).situacao

    def test_dona_nao_abre_a_fila(self):
        self.client.force_login(self.dona)
        for url in ("/pedidos/", self.url):
            self.assertRedirects(self.client.get(url), "/cliente/", fetch_redirect_response=False)
        for url in (self.url, self.url + "aprovar/"):
            self.assertEqual(self.client.post(url, {"acao": "devolver", "texto": "x"}).status_code, 403)
        self.assertEqual(self.situacao(), "enviado")

    def test_lista_mostra_pedidos_e_empresas_para_conferir(self):
        nova = Empresa.objects.create(razao_social="Nova Empresa LTDA", nr_insc="98.765.432/0001-98", cnae="",
                                      situacao="em_analise", ativa=False)
        r = self.client.get("/pedidos/")
        self.assertContains(r, "Empresa A LTDA")
        self.assertContains(r, "Contratei alguém")
        self.assertContains(r, f'href="/empresas/{nova.pk}/validar/"')

    def test_abrir_poe_em_analise(self):
        self.assertContains(self.client.get(self.url), "Ana Teste")
        self.assertEqual(self.situacao(), "em_analise")

    def test_devolver_e_cancelar_exigem_texto(self):
        for acao in ("devolver", "cancelar"):
            self.assertContains(self.client.post(self.url, {"acao": acao, "texto": " "}), "Escreva")
        self.assertNotIn(self.situacao(), ("devolvido", "cancelado"))
        self.client.post(self.url, {"acao": "devolver", "texto": "Falta a data de nascimento."})
        self.assertEqual(self.situacao(), "devolvido")
        m = self.p.mensagens.get()
        self.assertEqual((m.autor, m.texto), (self.staff, "Falta a data de nascimento."))

    def test_responder_com_anexo_nao_muda_a_situacao(self):
        self.client.post(self.url, {"texto": "Recebido, vou ver.", "arquivo": SimpleUploadedFile("modelo.pdf", PDF)})
        self.assertEqual(self.situacao(), "em_analise")
        self.assertEqual(self.p.anexos.get().enviado_por, self.staff)

    def test_anexo_da_dona_e_baixado_pelo_escritorio(self):
        a = anexar(self.p, SimpleUploadedFile("rg.pdf", PDF), self.dona)
        r = self.client.get(f"{self.url}anexos/{a.pk}/")
        self.assertEqual(b"".join(r.streaming_content), PDF)
        self.assertEqual(self.client.get(f"/pedidos/{self.p.pk + 99}/anexos/{a.pk}/").status_code, 404)

    def test_concluir_documento_e_duvida(self):
        doc = Pedido.objects.create(empresa=self.a, tipo="documento", respostas={"assunto": "atestado"})
        r = self.client.post(f"/pedidos/{doc.pk}/aprovar/")
        self.assertRedirects(r, "/pedidos/", fetch_redirect_response=False)
        self.assertEqual(self.situacao(doc), "concluido")
        duvida = Pedido.objects.create(empresa=self.a, tipo="duvida", situacao="devolvido", respostas={"texto": "?"})
        self.client.post(f"/pedidos/{duvida.pk}/aprovar/")
        self.assertEqual(self.situacao(duvida), "concluido")

    def test_aprovar_troca_empresa_e_abre_formulario(self):
        sessao = self.client.session
        sessao["empresa_id"] = self.b.pk
        sessao.save()
        r = self.client.post(self.url + "aprovar/")
        self.assertRedirects(r, f"/funcionarios/novo/?pedido={self.p.pk}", fetch_redirect_response=False)
        self.assertEqual(self.client.session["empresa_id"], self.a.pk)
        self.assertEqual(self.situacao(), "enviado")  # só aprova quando o formulário técnico for salvo

        alterar = Pedido.objects.create(empresa=self.a, tipo="alterar", funcionario=self.maria,
                                        respostas={"telefone": "65999990000"})
        r = self.client.post(f"/pedidos/{alterar.pk}/aprovar/")
        self.assertRedirects(r, f"/funcionarios/{self.maria.pk}/editar/?pedido={alterar.pk}",
                             fetch_redirect_response=False)

    def test_pedido_fechado_nao_aprova_nem_devolve(self):
        for situacao in ("aprovado", "concluido", "cancelado"):
            Pedido.objects.filter(pk=self.p.pk).update(situacao=situacao)
            with self.subTest(situacao=situacao):
                self.assertEqual(self.client.post(self.url + "aprovar/").status_code, 404)
                self.assertEqual(self.client.post(self.url, {"acao": "devolver", "texto": "x"}).status_code, 404)
                self.assertEqual(self.situacao(), situacao)

    def test_menu_mostra_contador(self):
        r = self.client.get("/")
        self.assertEqual(r.context["pedidos_para_ver"], 1)
        self.assertContains(r, 'href="/pedidos/"')
