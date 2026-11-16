"""Pedido, conversa e anexo: o que a dona manda fica no próprio pedido até o escritório aprovar."""

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from empresas.models import ArquivoPrivado
from esocial.models import Evento
from folha.tests.fabrica import empresa, funcionario
from portal.anexos import MAX_BYTES, anexar, tipo_do_arquivo
from portal.models import Mensagem, Pedido, concluir_os_aceitos

from .fabrica import dona, usar_banco_nos_anexos

PDF = b"%PDF-1.4\n1 0 obj\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 20


def arquivo(nome, conteudo):
    return SimpleUploadedFile(nome, conteudo)


class ModelosTests(TestCase):
    def setUp(self):
        usar_banco_nos_anexos(self)
        self.emp = empresa()
        self.dona = dona(self.emp)
        self.pedido = Pedido.objects.create(empresa=self.emp, criado_por=self.dona, tipo="duvida",
                                            respostas={"texto": "Posso dar folga no feriado?"})

    def test_mudar_grava_aviso_na_conversa(self):
        self.pedido.mudar("devolvido", None, "Falta a data.")
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.situacao, "devolvido")
        m = Mensagem.objects.get(pedido=self.pedido)
        self.assertEqual((m.autor, m.texto), (None, "Falta a data."))
        self.pedido.mudar("enviado", self.dona)  # sem texto, sem mensagem
        self.assertEqual(self.pedido.mensagens.count(), 1)

    def test_tipo_do_arquivo_aceita_pdf_jpg_png(self):
        self.assertEqual(tipo_do_arquivo(arquivo("a.pdf", PDF)), "application/pdf")
        self.assertEqual(tipo_do_arquivo(arquivo("foto.PNG", PNG)), "image/png")
        self.assertEqual(tipo_do_arquivo(arquivo("foto", JPG)), "image/jpeg")

    def test_recusa_executavel_com_nome_de_pdf(self):
        with self.assertRaisesMessage(ValidationError, "Envie foto (JPG ou PNG) ou PDF."):
            tipo_do_arquivo(arquivo("atestado.pdf", b"MZ\x90\x00" + b"\x00" * 20))

    def test_recusa_maior_que_5mb(self):
        with self.assertRaisesMessage(ValidationError, "5 MB"):
            tipo_do_arquivo(arquivo("grande.pdf", PDF + b"\x00" * MAX_BYTES))

    def test_anexo_fica_no_banco_com_nome_seguro(self):
        a = anexar(self.pedido, arquivo("../../atestado da Maria.pdf", PDF), self.dona)
        self.assertEqual((a.nome, a.tipo_conteudo, a.tamanho), ("atestado da Maria.pdf", "application/pdf", len(PDF)))
        guardado = ArquivoPrivado.objects.get()
        self.assertTrue(guardado.nome.startswith(f"anexos/pedido_{self.pedido.pk}/"))
        self.assertTrue(guardado.nome.endswith(".pdf"))
        self.assertNotIn("Maria", guardado.nome)
        self.assertEqual(bytes(guardado.conteudo), PDF)
        with a.arquivo.open("rb") as f:
            self.assertEqual(f.read(), PDF)

    def test_concluir_os_aceitos(self):
        func = funcionario(self.emp)
        p = Pedido.objects.create(empresa=self.emp, tipo="contratei", situacao="aprovado", funcionario=func)
        outro = Pedido.objects.create(empresa=self.emp, tipo="contratei", situacao="aprovado")  # sem vínculo
        ev = Evento.objects.create(empresa=self.emp, tipo="S-2200", descricao="Admissão", id_evento="ID1",
                                   xml="<x/>", funcionario=func, status="rejeitado")
        concluir_os_aceitos(Pedido.objects.all())
        p.refresh_from_db()
        self.assertEqual(p.situacao, "aprovado")

        ev.status = "aceito"
        ev.save()
        concluir_os_aceitos(Pedido.objects.all())
        p.refresh_from_db()
        outro.refresh_from_db()
        self.assertEqual((p.situacao, outro.situacao), ("concluido", "aprovado"))
        self.assertIn("eSocial", p.mensagens.get().texto)
