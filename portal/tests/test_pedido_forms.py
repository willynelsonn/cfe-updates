"""Formulários que a dona preenche: só pessoas da empresa dela, respostas guardadas em JSON e resumo legível."""

import json
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from folha.tests.fabrica import funcionario
from portal.models import Pedido
from portal.pedido_forms import AlterarForm, ContrateiForm, DocumentoForm, FeriasPedidoForm, SairForm, resumo

from .fabrica import duas_empresas

HOJE = timezone.localdate()


class FormulariosTests(TestCase):
    def setUp(self):
        self.a, self.b = duas_empresas()
        self.maria = funcionario(self.a)
        self.de_b = funcionario(self.b, nome="Pessoa da Empresa B", cpf="111.444.777-35")

    def test_pessoa_de_outra_empresa_e_recusada(self):
        dados = {"ultimo_dia": HOJE.isoformat(), "quem_pediu": "pessoa", "aviso": "nao_sei"}
        self.assertFalse(SairForm({**dados, "funcionario": self.de_b.pk}, empresa=self.a).is_valid())
        form = SairForm({**dados, "funcionario": self.maria.pk}, empresa=self.a)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["funcionario"], self.maria)

    def test_ferias_no_passado_e_recusada(self):
        base = {"funcionario": self.maria.pk, "dias": "30"}
        form = FeriasPedidoForm({**base, "inicio": (HOJE - timedelta(days=1)).isoformat()}, empresa=self.a)
        self.assertIn("inicio", form.errors)
        futuro = (HOJE + timedelta(days=40)).isoformat()
        form = FeriasPedidoForm({**base, "inicio": futuro, "vender_10": "on"}, empresa=self.a)
        self.assertIn("no máximo 20 dias", str(form.errors))
        self.assertTrue(FeriasPedidoForm({**base, "inicio": futuro, "dias": "20", "vender_10": "on"},
                                         empresa=self.a).is_valid())

    def test_alterar_sem_nenhuma_mudanca_e_recusado(self):
        form = AlterarForm({"funcionario": self.maria.pk, "observacao": "só isso"}, empresa=self.a)
        self.assertIn("pelo menos uma mudança", str(form.errors))
        self.assertTrue(AlterarForm({"funcionario": self.maria.pk, "telefone": "65999990000"}, empresa=self.a).is_valid())

    def test_documento_exige_arquivo(self):
        self.assertIn("arquivo", DocumentoForm({"assunto": "atestado"}, empresa=self.a).errors)
        pdf = SimpleUploadedFile("atestado.pdf", b"%PDF-1.4 teste")
        self.assertTrue(DocumentoForm({"assunto": "atestado"}, {"arquivo": pdf}, empresa=self.a).is_valid())

    def test_respostas_vao_para_json(self):
        form = ContrateiForm({
            "nome": "Ana Teste", "cpf": "123.456.789-09", "data_nascimento": "1995-08-15", "cep": "78000-000",
            "salario": "2.500,00", "horario": "segunda a sexta, 8h às 17h", "funcao": "atender no balcão",
            "data_inicio": "2026-12-01",
        }, empresa=self.a)
        self.assertTrue(form.is_valid(), form.errors)
        r = form.respostas()
        json.dumps(r)
        self.assertEqual((r["salario"], r["data_inicio"], r["cpf"]), ("2500.00", "2026-12-01", "12345678909"))
        self.assertIs(r["vale_transporte"], False)
        self.assertNotIn("arquivo", r)

    def test_resumo_mostra_rotulos_simples(self):
        p = Pedido(empresa=self.a, tipo="sair", funcionario=self.maria,
                   respostas={"ultimo_dia": "2026-12-10", "quem_pediu": "pessoa", "aviso": "trabalha", "observacao": ""})
        linhas = dict(resumo(p))
        self.assertEqual(linhas["Quem pediu para sair"], "A própria pessoa pediu")
        self.assertEqual(linhas["Último dia de trabalho"], "10/12/2026")
        self.assertNotIn("Quer contar mais alguma coisa?", linhas)
        p = Pedido(empresa=self.a, tipo="alterar", respostas={"salario": "3100.00"})
        self.assertEqual(dict(resumo(p))["Novo salário por mês (R$)"], "R$ 3.100,00")
