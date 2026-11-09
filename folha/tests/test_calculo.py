from datetime import date
from decimal import Decimal as D

from django.test import SimpleTestCase, TestCase

from folha import calculo as c
from folha.models import Lancamento, Rubrica
from folha.servico import calcular_competencia, resumo_encargos
from folha.tabelas import tabelas_do_ano

from . import fabrica

T26 = tabelas_do_ano(2026)


class INSSTest(SimpleTestCase):
    def test_salario_minimo(self):
        self.assertEqual(c.calcular_inss(D("1621.00"), T26).valor, D("121.58"))

    def test_progressivo_3000(self):
        # 1621*7,5% + (2902,84-1621)*9% + (3000-2902,84)*12% = 121,575 + 115,3656 + 11,6592
        self.assertEqual(c.calcular_inss(D("3000"), T26).valor, D("248.60"))

    def test_teto(self):
        self.assertEqual(c.calcular_inss(D("8475.55"), T26).valor, D("988.09"))
        self.assertEqual(c.calcular_inss(D("20000"), T26).valor, D("988.09"))


class IRRFTest(SimpleTestCase):
    def test_isento_ate_5000_com_redutor_2026(self):
        inss = c.calcular_inss(D("5000"), T26).valor
        r = c.calcular_irrf(D("5000"), inss, 0, T26)
        self.assertTrue(r.usou_desconto_simplificado)
        self.assertEqual(r.imposto_tabela, D("312.89"))
        self.assertEqual(r.reducao_lei_15270, D("312.89"))
        self.assertEqual(r.valor, D("0.00"))

    def test_reducao_parcial_6000(self):
        inss = c.calcular_inss(D("6000"), T26).valor  # 641,51
        r = c.calcular_irrf(D("6000"), inss, 0, T26)
        # base 5358,49 -> 27,5% - 908,73 = 564,85 ; redução 978,62 - 0,133145*6000 = 179,75
        self.assertEqual(r.base, D("5358.49"))
        self.assertEqual(r.imposto_tabela, D("564.85"))
        self.assertEqual(r.reducao_lei_15270, D("179.75"))
        self.assertEqual(r.valor, D("385.10"))

    def test_sem_reducao_acima_7350(self):
        inss = c.calcular_inss(D("10000"), T26).valor
        r = c.calcular_irrf(D("10000"), inss, 1, T26)
        self.assertEqual(r.reducao_lei_15270, D("0"))
        base = D("10000") - inss - D("189.59")
        self.assertEqual(r.valor, c.r2(base * D("0.275") - D("908.73")))

    def test_2025_sem_redutor(self):
        t25 = tabelas_do_ano(2025)
        r = c.calcular_irrf(D("5000"), c.calcular_inss(D("5000"), t25).valor, 0, t25)
        self.assertGreater(r.valor, 0)
        self.assertEqual(r.reducao_lei_15270, 0)

    def test_dispensa_ate_10_reais(self):
        r = c.calcular_irrf(D("2500"), D("0"), 0, tabelas_do_ano(2025))
        self.assertEqual(r.valor, 0)  # imposto calculado abaixo de R$ 10


class AuxiliaresTest(SimpleTestCase):
    def test_dias_trabalhados(self):
        self.assertEqual(c.dias_trabalhados(2026, 10, date(2025, 1, 1), None), 30)
        self.assertEqual(c.dias_trabalhados(2026, 10, date(2026, 10, 16), None), 15)
        self.assertEqual(c.dias_trabalhados(2026, 2, date(2025, 1, 1), date(2026, 2, 28)), 30)
        self.assertEqual(c.dias_trabalhados(2026, 10, date(2025, 1, 1), date(2026, 10, 10)), 10)
        self.assertEqual(c.dias_trabalhados(2026, 10, date(2026, 11, 1), None), 0)

    def test_salario_familia(self):
        self.assertEqual(c.salario_familia(D("1900"), 2, T26), D("135.08"))
        self.assertEqual(c.salario_familia(D("2000"), 2, T26), 0)

    def test_aviso_previo(self):
        self.assertEqual(c.aviso_previo_dias(date(2020, 1, 1), date(2026, 1, 1)), 48)
        self.assertEqual(c.aviso_previo_dias(date(1990, 1, 1), date(2026, 1, 1)), 90)


class FolhaCompletaTest(TestCase):
    def test_calcula_holerite_com_horas_extras_e_salario_familia(self):
        emp = fabrica.empresa()
        f1 = fabrica.funcionario(emp)
        f2 = fabrica.funcionario(emp, matricula="0002", nome="José Souza", cpf="111.444.777-35", salario=D("1700"))
        fabrica.filho(f2, cpf="")
        comp = fabrica.competencia(emp)
        he = Rubrica.objects.get(empresa=emp, papel="he50")
        Lancamento.objects.create(competencia=comp, funcionario=f1, rubrica=he, quantidade=D("10"))

        avisos = calcular_competencia(comp)
        self.assertEqual(avisos, [])
        h1 = comp.holerites.get(funcionario=f1)
        # hora = 3000/220 = 13,6364 ; HE 50% x 10h = 204,55
        valores = {i.rubrica.codigo: i.valor for i in h1.itens.all()}
        self.assertEqual(valores["1010"], D("204.55"))
        # outubro/2026: 31 dias, 4 domingos -> 27 úteis, 4 DSR ; 204,55/27*4 = 30,30
        self.assertEqual(valores["1020"], D("30.30"))
        self.assertEqual(h1.base_inss, D("3234.85"))
        self.assertEqual(h1.liquido, h1.total_proventos - h1.total_descontos)
        self.assertEqual(h1.valor_irrf, 0)  # abaixo de R$ 5.000 em 2026
        self.assertEqual(h1.valor_fgts, D("258.79"))

        h2 = comp.holerites.get(funcionario=f2)
        self.assertEqual(h2.salario_familia, D("67.54"))

        resumo = resumo_encargos(comp)
        self.assertEqual(resumo.funcionarios, 2)
        self.assertEqual(resumo.cpp_patronal, c.r2((h1.base_inss + h2.base_inss) * D("0.20")))
