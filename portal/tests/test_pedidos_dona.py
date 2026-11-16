"""A dona faz pedidos pelo portal. Nada toca funcionário ou eSocial; nada de outra empresa aparece (404)."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from esocial.models import Evento
from folha.tests.fabrica import funcionario
from pessoal.models import Funcionario
from portal.anexos import anexar
from portal.models import Pedido

from .fabrica import dona, duas_empresas, usar_banco_nos_anexos

PDF = b"%PDF-1.4 teste"
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 20
CONTRATEI = {
    "nome": "Ana Teste", "cpf": "123.456.789-09", "data_nascimento": "1995-08-15", "cep": "78000-000",
    "salario": "2.500,00", "horario": "segunda a sexta, 8h às 17h", "funcao": "atender no balcão",
    "data_inicio": "2026-12-01",
}
SAIR = {"ultimo_dia": "2026-12-10", "quem_pediu": "pessoa", "aviso": "trabalha"}


class PedidosDonaTests(TestCase):
    def setUp(self):
        usar_banco_nos_anexos(self)
        self.a, self.b = duas_empresas()
        self.dona_a = dona(self.a)
        self.dona_b = dona(self.b, email="outra@exemplo.com")
        self.maria = funcionario(self.a)
        self.de_b = funcionario(self.b, nome="Pessoa da Empresa B", cpf="111.444.777-35")
        self.client.force_login(self.dona_a)

    def pedido_de(self, emp, func, **kw):
        return Pedido.objects.create(empresa=emp, tipo="sair", funcionario=func, respostas=dict(SAIR), **kw)

    def test_contratei_nao_mexe_em_funcionario_nem_esocial(self):
        antes = Funcionario.objects.count()
        r = self.client.post("/cliente/pedidos/novo/contratei/",
                             {**CONTRATEI, "arquivo": SimpleUploadedFile("rg.jpg", JPG)})
        p = Pedido.objects.get()
        self.assertRedirects(r, f"/cliente/pedidos/{p.pk}/", fetch_redirect_response=False)
        self.assertEqual((p.empresa, p.criado_por, p.tipo, p.situacao), (self.a, self.dona_a, "contratei", "enviado"))
        self.assertEqual(p.respostas["nome"], "Ana Teste")
        self.assertEqual(p.anexos.get().nome, "rg.jpg")
        self.assertEqual(Funcionario.objects.count(), antes)
        self.assertEqual(Evento.objects.count(), 0)
        self.assertContains(self.client.get(r.url), "Ana Teste")

    def test_sair_guarda_a_pessoa(self):
        self.client.post("/cliente/pedidos/novo/sair/", {**SAIR, "funcionario": self.maria.pk})
        p = Pedido.objects.get()
        self.assertEqual(p.funcionario, self.maria)
        self.assertIsNone(Funcionario.objects.get(pk=self.maria.pk).data_desligamento)

    def test_anexo_do_pedido_e_baixado_so_pela_dona_da_empresa(self):
        p = self.pedido_de(self.a, self.maria)
        a = anexar(p, SimpleUploadedFile("atestado.pdf", PDF), self.dona_a)
        url = f"/cliente/pedidos/{p.pk}/anexos/{a.pk}/"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), PDF)
        self.assertIn('attachment; filename="atestado.pdf"', r["Content-Disposition"])
        self.client.force_login(self.dona_b)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_empresa_em_analise_so_documento_e_duvida(self):
        self.a.situacao, self.a.ativa = "em_analise", False
        self.a.save()
        r = self.client.get("/cliente/pedidos/novo/")
        self.assertContains(r, "Mandar documento")
        self.assertNotContains(r, "Contratei alguém")
        self.assertEqual(self.client.get("/cliente/pedidos/novo/ferias/").status_code, 404)
        self.assertEqual(self.client.get("/cliente/pedidos/novo/documento/").status_code, 200)
        self.assertEqual(self.client.get("/cliente/pedidos/novo/qualquer/").status_code, 404)

    def test_devolvido_mensagem_reenvia(self):
        p = self.pedido_de(self.a, self.maria, situacao="devolvido")
        r = self.client.post(f"/cliente/pedidos/{p.pk}/", {"texto": "O último dia é 12/12."})
        self.assertRedirects(r, f"/cliente/pedidos/{p.pk}/", fetch_redirect_response=False)
        p.refresh_from_db()
        self.assertEqual(p.situacao, "enviado")
        m = p.mensagens.get()
        self.assertEqual((m.autor, m.texto), (self.dona_a, "O último dia é 12/12."))

    def test_corrigir_so_quando_devolvido(self):
        p = self.pedido_de(self.a, self.maria)
        self.assertEqual(self.client.get(f"/cliente/pedidos/{p.pk}/corrigir/").status_code, 404)
        p.mudar("devolvido", None, "Confira o último dia.")
        self.assertContains(self.client.get(f"/cliente/pedidos/{p.pk}/corrigir/"), 'value="2026-12-10"')
        self.client.post(f"/cliente/pedidos/{p.pk}/corrigir/", {**SAIR, "ultimo_dia": "2026-12-12",
                                                                "funcionario": self.maria.pk})
        p.refresh_from_db()
        self.assertEqual((p.situacao, p.respostas["ultimo_dia"]), ("enviado", "2026-12-12"))

    def test_cancelar_so_aberto(self):
        p = self.pedido_de(self.a, self.maria)
        self.client.post(f"/cliente/pedidos/{p.pk}/cancelar/")
        p.refresh_from_db()
        self.assertEqual(p.situacao, "cancelado")
        aprovado = self.pedido_de(self.a, self.maria, situacao="aprovado")
        self.assertEqual(self.client.post(f"/cliente/pedidos/{aprovado.pk}/cancelar/").status_code, 404)

    def test_isolamento_404_em_todas_as_rotas(self):
        p = self.pedido_de(self.b, self.de_b, situacao="devolvido")
        a = anexar(p, SimpleUploadedFile("doc.pdf", PDF), self.dona_b)
        base = f"/cliente/pedidos/{p.pk}/"
        for metodo, url, dados in [
            ("get", base, {}), ("post", base, {"texto": "oi"}), ("get", base + "corrigir/", {}),
            ("post", base + "corrigir/", {**SAIR, "funcionario": self.maria.pk}), ("post", base + "cancelar/", {}),
            ("get", f"{base}anexos/{a.pk}/", {}),
        ]:
            with self.subTest(metodo=metodo, url=url):
                self.assertEqual(getattr(self.client, metodo)(url, dados).status_code, 404)
        p.refresh_from_db()
        self.assertEqual((p.situacao, p.mensagens.count()), ("devolvido", 0))

    def test_lista_so_da_empresa(self):
        self.pedido_de(self.a, self.maria)
        self.pedido_de(self.b, self.de_b)
        r = self.client.get("/cliente/pedidos/")
        self.assertContains(r, "Maria da Silva")
        self.assertNotContains(r, "Pessoa da Empresa B")

    def test_escritorio_vai_para_o_painel(self):
        from django.contrib.auth.models import User

        self.client.force_login(User.objects.create_user("escritorio", password="x", is_staff=True))
        self.assertRedirects(self.client.get("/cliente/pedidos/"), "/", fetch_redirect_response=False)
