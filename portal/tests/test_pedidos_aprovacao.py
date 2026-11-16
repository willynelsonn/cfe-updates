"""Aprovar = salvar o formulário técnico aberto com ?pedido=<id>. Só aí o pedido vira cadastro de verdade."""

from django.contrib.auth.models import User
from django.test import TestCase

from esocial.models import Evento
from esocial.servico import gerar_admissao
from folha.models import Ferias, Rescisao
from folha.tests.fabrica import funcionario
from pessoal.models import Funcionario
from portal.models import Pedido

from .fabrica import dona, duas_empresas

NOVA = {
    "matricula": "0002", "nome": "Ana Teste", "cpf": "123.456.789-09", "data_nascimento": "1995-08-15", "sexo": "F",
    "raca_cor": 1, "grau_instrucao": "07", "cep": "78000-000", "logradouro": "Rua Exemplo", "numero": "10",
    "cod_municipio": "5103403", "uf": "MT", "data_admissao": "2026-12-01", "categoria": "101", "salario": "2500.00",
    "tipo_contrato": 1, "horas_semanais": "44", "tipo_jornada": 3, "descricao_jornada": "seg a sex",
    "insalubridade": 0, "vale_transporte": "0", "beneficios_mensais": "0",
}


class AprovacaoTests(TestCase):
    def setUp(self):
        self.a, self.b = duas_empresas()
        self.dona = dona(self.a)
        self.maria = funcionario(self.a)
        self.client.force_login(User.objects.create_user("escritorio", password="x", is_staff=True))
        self.na_empresa(self.a)

    def na_empresa(self, emp):
        sessao = self.client.session
        sessao["empresa_id"] = emp.pk
        sessao.save()

    def pedido(self, emp=None, **kw):
        return Pedido.objects.create(empresa=emp or self.a, criado_por=self.dona, **kw)

    def dados_do_formulario(self, resp):
        form = resp.context["form"]
        return {nome: v for nome in form.fields if (v := form[nome].value()) is not None}

    def test_contratei_preenche_e_aprova_ao_salvar(self):
        p = self.pedido(tipo="contratei", respostas={"nome": "Ana Teste", "cpf": "12345678909", "salario": "2500.00",
                                                     "data_inicio": "2026-12-01", "horario": "seg a sex"})
        url = f"/funcionarios/novo/?pedido={p.pk}"
        r = self.client.get(url)
        self.assertContains(r, f"Pedido nº {p.pk} da cliente")
        self.assertContains(r, 'value="Ana Teste"')
        self.assertContains(r, 'value="2026-12-01"')
        r = self.client.post(url, {**NOVA, "cargo": self.maria.cargo.pk})
        self.assertEqual(r.status_code, 302, r.context and r.context["form"].errors)
        p.refresh_from_db()
        self.assertEqual((p.situacao, p.funcionario), ("aprovado", Funcionario.objects.get(cpf="12345678909")))
        self.assertIsNone(p.mensagens.get().autor)

    def test_pedido_de_outra_empresa_nao_aprova(self):
        p = self.pedido(self.b, tipo="contratei", respostas={"nome": "Pessoa da Empresa B"})
        url = f"/funcionarios/novo/?pedido={p.pk}"
        self.assertNotContains(self.client.get(url), "Pessoa da Empresa B")
        self.client.post(url, {**NOVA, "cargo": self.maria.cargo.pk})
        p.refresh_from_db()
        self.assertEqual((p.situacao, p.funcionario), ("enviado", None))

    def test_ferias_aprova_com_vinculo(self):
        p = self.pedido(tipo="ferias", funcionario=self.maria,
                        respostas={"inicio": "2027-01-11", "dias": 20, "vender_10": True})
        url = f"/folha/ferias/nova/?pedido={p.pk}"
        r = self.client.get(url)
        self.assertContains(r, 'value="2027-01-11"')
        self.assertContains(r, 'value="2025-03-01"')  # período aquisitivo sugerido
        r = self.client.post(url, self.dados_do_formulario(r))
        fe = Ferias.objects.get()
        self.assertEqual((fe.dias, fe.dias_abono), (20, 10))
        p.refresh_from_db()
        self.assertEqual((p.situacao, p.ferias), ("aprovado", fe))

    def test_rescisao_aprova_com_vinculo(self):
        p = self.pedido(tipo="sair", funcionario=self.maria,
                        respostas={"ultimo_dia": "2026-12-10", "quem_pediu": "empresa", "aviso": "nao_trabalha"})
        url = f"/folha/rescisoes/nova/?pedido={p.pk}"
        r = self.client.get(url)
        self.assertContains(r, '<option value="02" selected>')
        self.assertContains(r, 'value="2026-12-10"')
        r = self.client.post(url, {**self.dados_do_formulario(r), "data_aviso": "2026-12-10", "saldo_fgts": "0"})
        resc = Rescisao.objects.get()
        self.assertEqual((resc.motivo, resc.tipo_aviso), ("02", "indenizado"))
        p.refresh_from_db()
        self.assertEqual((p.situacao, p.rescisao), ("aprovado", resc))

    def test_alterar_conclui(self):
        joao = funcionario(self.a, matricula="0002", nome="João Teste", cpf="111.444.777-35")
        p = self.pedido(tipo="alterar", funcionario=self.maria,
                        respostas={"telefone": "65999990000", "banco_pix": "pix-da-maria"})
        self.assertNotContains(self.client.get(f"/funcionarios/{joao.pk}/editar/?pedido={p.pk}"), "Pedido nº")
        url = f"/funcionarios/{self.maria.pk}/editar/?pedido={p.pk}"
        r = self.client.get(url)
        self.assertContains(r, 'value="65999990000"')
        self.assertContains(r, "pix-da-maria")  # o que não tem campo próprio aparece no resumo
        self.assertEqual(self.client.post(url, self.dados_do_formulario(r)).status_code, 302)
        self.maria.refresh_from_db()
        p.refresh_from_db()
        self.assertEqual((self.maria.telefone, p.situacao), ("65999990000", "concluido"))

    def test_lista_conclui_quando_evento_aceito(self):
        p = self.pedido(tipo="contratei", situacao="aprovado", funcionario=self.maria)
        Evento.objects.create(empresa=self.a, tipo="S-2200", descricao="Admissão", id_evento="ID1", xml="<x/>",
                              funcionario=self.maria, status="aceito")
        self.client.force_login(self.dona)
        self.assertContains(self.client.get("/cliente/pedidos/"), "Concluído")
        p.refresh_from_db()
        self.assertEqual(p.situacao, "concluido")

    def test_alterar_salario_fica_aprovado_ate_o_esocial_aceitar(self):
        Evento.objects.filter(pk=gerar_admissao(self.maria).pk).update(status="aceito")
        p = self.pedido(tipo="alterar", funcionario=self.maria,
                        respostas={"salario": "3300.00", "a_partir_de": "2026-11-01"})
        url = f"/funcionarios/{self.maria.pk}/editar/?pedido={p.pk}"
        r = self.client.get(url)
        self.assertContains(r, 'value="2026-11-01"')  # a data da mudança vem do pedido
        self.assertEqual(self.client.post(url, self.dados_do_formulario(r)).status_code, 302)
        p.refresh_from_db()
        chave = f"S-2206:func:{self.maria.pk}:2026-11-01"
        self.assertEqual((p.situacao, p.eventos_esocial), ("aprovado", [chave]))
        self.client.force_login(self.dona)
        self.assertNotContains(self.client.get("/cliente/pedidos/"), "Concluído")
        Evento.objects.filter(chave=chave).update(status="aceito")
        self.assertContains(self.client.get("/cliente/pedidos/"), "Concluído")
        p.refresh_from_db()
        self.assertEqual(p.situacao, "concluido")
