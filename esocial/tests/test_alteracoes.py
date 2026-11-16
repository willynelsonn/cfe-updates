"""S-2205 (dados pessoais) e S-2206 (contrato): XML válido no esquema oficial e escolha do evento pelo que mudou."""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from esocial import xml_eventos as xe
from esocial.models import Evento
from esocial.servico import chave_admissao, gerar_admissao, gerar_alteracoes, regerar
from esocial.validacao import validar_evento
from folha.tests import fabrica

DIA = date(2026, 11, 16)


class XmlAlteracoesTest(TestCase):
    def setUp(self):
        self.emp = fabrica.empresa()
        self.func = fabrica.funcionario(self.emp)
        fabrica.filho(self.func)

    def xml(self, tipo, root):
        xml = xe.para_bytes(root)
        self.assertEqual(validar_evento(tipo, xml, assinado=False), [])
        return xml.decode()

    def test_s2205_valido_no_xsd(self):
        xml = self.xml("S-2205", xe.s2205(self.func, DIA)[1])
        for trecho in ("<dtAlteracao>2026-11-16</dtAlteracao>", "<nmTrab>Maria da Silva</nmTrab>",
                       "<paisNac>105</paisNac>", "<nmDep>João da Silva</nmDep>", "<indRetif>1</indRetif>"):
            self.assertIn(trecho, xml)

    def test_s2206_valido_no_xsd(self):
        self.func.salario = Decimal("2750.00")
        xml = self.xml("S-2206", xe.s2206(self.func, DIA)[1])
        for trecho in ("<dtAlteracao>2026-11-16</dtAlteracao>", "<vrSalFx>2750.00</vrSalFx>", "<nmCargo>Padeiro</nmCargo>",
                       "<tmpParc>0</tmpParc>", f"<matricula>{self.func.matricula}</matricula>"):
            self.assertIn(trecho, xml)

    def test_retificacao_leva_recibo(self):
        xml = self.xml("S-2205", xe.s2205(self.func, DIA, recibo="1.2.0000000000000000001")[1])
        self.assertIn("<indRetif>2</indRetif>", xml)
        self.assertIn("<nrRecibo>1.2.0000000000000000001</nrRecibo>", xml)

    def test_tmp_parc(self):
        def tmp(horas, categoria):
            self.func.horas_semanais, self.func.categoria = Decimal(horas), categoria
            return self.xml("S-2206", xe.s2206(self.func, DIA)[1])

        self.assertIn("<tmpParc>2</tmpParc>", tmp("20", "101"))
        self.assertIn("<tmpParc>1</tmpParc>", tmp("20", "104"))
        self.assertIn("<tmpParc>0</tmpParc>", tmp("44", "101"))


class GerarAlteracoesTest(TestCase):
    def setUp(self):
        self.emp = fabrica.empresa()
        self.func = fabrica.funcionario(self.emp)
        self.adm = gerar_admissao(self.func)
        Evento.objects.filter(pk=self.adm.pk).update(status="aceito", recibo="1.1.0000000000000000001")

    def test_pix_banco_e_vt_nao_vao_ao_esocial(self):
        self.assertEqual(gerar_alteracoes(self.func, {"chave_pix", "banco", "vale_transporte"}, DIA), [])

    def test_salario_gera_s2206_depois_da_admissao(self):
        [ev] = gerar_alteracoes(self.func, {"salario"}, DIA)
        self.assertEqual((ev.tipo, ev.status, ev.chave, ev.depende, ev.funcionario),
                         ("S-2206", "pendente", f"S-2206:func:{self.func.pk}:2026-11-16", [chave_admissao(self.func)],
                          self.func))

    def test_endereco_gera_s2205(self):
        [ev] = gerar_alteracoes(self.func, {"logradouro"}, DIA)
        self.assertEqual((ev.tipo, ev.status), ("S-2205", "pendente"))

    def test_dados_pessoais_e_contrato_geram_os_dois(self):
        eventos = gerar_alteracoes(self.func, {"telefone", "cargo"}, DIA)
        self.assertEqual([e.tipo for e in eventos], ["S-2205", "S-2206"])

    def test_admissao_ainda_na_fila_e_gerada_de_novo(self):
        Evento.objects.filter(pk=self.adm.pk).update(status="pendente")
        [ev] = gerar_alteracoes(self.func, {"salario"}, DIA)
        self.assertEqual(ev.tipo, "S-2200")
        self.assertFalse(Evento.objects.filter(pk=self.adm.pk).exists())

    def test_sem_admissao_no_esocial_nada_sai(self):
        self.adm.delete()
        self.assertEqual(gerar_alteracoes(self.func, {"salario"}, DIA), [])

    def test_ja_cadastrado_por_outro_sistema(self):
        self.adm.delete()
        self.func.esocial_ja_cadastrado = True
        self.func.save()
        [ev] = gerar_alteracoes(self.func, {"salario"}, DIA)
        self.assertEqual((ev.status, ev.depende), ("pendente", []))

    def test_raca_nao_informada_fica_com_erro_e_gerar_de_novo_corrige(self):
        self.func.raca_cor = 6
        self.func.save()
        [ev] = gerar_alteracoes(self.func, {"raca_cor"}, DIA)
        self.assertEqual(ev.status, "erro")
        self.assertIn("Raça/cor", ev.mensagens[0])
        self.func.raca_cor = 3
        self.func.save()
        novo = regerar(ev)
        self.assertEqual((novo.tipo, novo.status, novo.chave), ("S-2205", "pendente", ev.chave))
        self.assertIn("<dtAlteracao>2026-11-16</dtAlteracao>", novo.xml)

    def test_mesma_data_ja_aceita_vira_retificacao(self):
        [ev] = gerar_alteracoes(self.func, {"salario"}, DIA)
        Evento.objects.filter(pk=ev.pk).update(status="aceito", recibo="1.2.0000000000000000009")
        [novo] = gerar_alteracoes(self.func, {"salario"}, DIA)
        self.assertEqual(novo.status, "pendente")
        self.assertIn("<nrRecibo>1.2.0000000000000000009</nrRecibo>", novo.xml)
