"""S-2205 (dados pessoais) e S-2206 (contrato): XML válido no esquema oficial e escolha do evento pelo que mudou."""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from esocial import xml_eventos as xe
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
