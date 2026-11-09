from datetime import date
from decimal import Decimal as D

from django.test import TestCase

from folha import calculo as c
from folha.conformidade import CRITICO, problemas_ferias, verificar
from folha.forms import FeriasForm
from folha.models import Competencia, Ferias
from folha.servico import calcular_competencia, calcular_ferias

from . import fabrica


def itens(hol):
    return {i.rubrica.codigo: i.valor for i in hol.itens.all()}


class FeriasTest(TestCase):
    def setUp(self):
        self.emp = fabrica.empresa()
        self.func = fabrica.funcionario(self.emp)  # R$ 3.000, admitida em 01/03/2025

    def ferias(self, **kw):
        dados = dict(funcionario=self.func, aquisitivo_inicio=date(2025, 3, 1), aquisitivo_fim=date(2026, 2, 28),
                     inicio=date(2026, 11, 3), dias=30, data_pagamento=date(2026, 10, 30),
                     data_aviso=date(2026, 10, 1))
        dados.update(kw)
        return calcular_ferias(Ferias.objects.create(**dados))

    def test_ferias_pagas_no_mes_anterior(self):
        fe = self.ferias()
        self.assertEqual(fe.valor_ferias, D("3000.00"))
        self.assertEqual(fe.valor_terco, D("1000.00"))
        self.assertEqual([(p["mes"], p["dias"]) for p in fe.parcelas], [(11, 28), (12, 2)])
        # INSS por mês de gozo: nov 360,60-15,00 ; dez 256,60-227,69
        self.assertEqual(fe.valor_inss, D("374.51"))
        self.assertEqual(fe.valor_irrf, 0)  # isento pela redução de 2026
        self.assertEqual(fe.liquido, D("3625.49"))

        out = fabrica.competencia(self.emp, mes=10)
        calcular_competencia(out)
        recibo = out.holerites.get(tipo="ferias")
        self.assertEqual(recibo.liquido, D("3625.49"))
        self.assertIn("1104", itens(recibo))  # adiantamento de férias (natureza 1015)
        self.assertNotIn("1100", itens(recibo))
        self.assertEqual(out.holerites.get(tipo="folha").dias_trabalhados, 30)

        nov = fabrica.competencia(self.emp, mes=11)
        calcular_competencia(nov)
        folha = nov.holerites.get(tipo="folha")
        v = itens(folha)
        self.assertEqual(folha.dias_trabalhados, 2)
        self.assertEqual(v["1000"], D("200.00"))
        self.assertEqual(v["1102"], D("2800.00"))
        self.assertEqual(v["1103"], D("933.33"))
        self.assertEqual(v["9221"], D("3387.73"))
        self.assertEqual(v["9201"], D("360.60"))
        self.assertEqual(folha.liquido, D("185.00"))  # nunca negativo
        self.assertEqual(folha.base_fgts, D("3933.33"))

        dez = fabrica.competencia(self.emp, mes=12)
        calcular_competencia(dez)
        self.assertEqual(dez.holerites.get(tipo="folha").liquido, D("2572.31"))

    def test_ferias_pagas_no_mes_do_gozo_com_abono(self):
        fe = self.ferias(inicio=date(2026, 11, 10), dias=20, dias_abono=10, data_pagamento=date(2026, 11, 6),
                         data_aviso=date(2026, 10, 9))
        self.assertEqual(fe.valor_abono, D("1333.33"))
        self.assertEqual(fe.valor_inss, D("253.60"))
        self.assertEqual(fe.liquido, D("3746.40"))
        nov = fabrica.competencia(self.emp, mes=11)
        calcular_competencia(nov)
        recibo = nov.holerites.get(tipo="ferias")
        self.assertEqual(set(itens(recibo)), {"1100", "1101", "1105", "9206"})
        folha = nov.holerites.get(tipo="folha")
        self.assertEqual(itens(folha)["9201"], D("75.00"))  # 328,60 do mês - 253,60 já retidos
        self.assertEqual(folha.base_inss, D("3666.67"))

    def test_irrf_de_ferias_alto(self):
        self.func.salario = D("9000")
        self.func.save()
        fe = self.ferias(inicio=date(2026, 11, 10), data_pagamento=date(2026, 11, 6), data_aviso=date(2026, 10, 9))
        # base = 12.000 - INSS retido (maior que o simplificado) ; 27,5% - 908,73 ; sem redução (> 7.350)
        base = D("12000") - fe.valor_inss
        self.assertEqual(fe.valor_irrf, c.r2(base * D("0.275") - D("908.73")))

    def test_regras_clt(self):
        fe = Ferias(funcionario=self.func, aquisitivo_inicio=date(2025, 3, 1), aquisitivo_fim=date(2026, 2, 28),
                    inicio=date(2026, 11, 6), dias=4, dias_abono=11, data_pagamento=date(2026, 11, 5),
                    data_aviso=date(2026, 11, 1))
        titulos = {t for n, t, d, b in problemas_ferias(fe) if n == CRITICO}
        self.assertIn("período menor que 5 dias", titulos)
        self.assertIn("abono acima de 1/3", titulos)
        self.assertIn("pagamento fora do prazo", titulos)
        atencao = {t for n, t, d, b in problemas_ferias(fe) if n != CRITICO}
        self.assertIn("início nos 2 dias antes do repouso semanal", atencao)  # sexta-feira
        self.assertIn("aviso com menos de 30 dias", atencao)

    def test_dias_de_direito_por_faltas(self):
        self.assertEqual([c.dias_direito_ferias(f) for f in (5, 6, 14, 15, 23, 24, 32, 33)],
                         [30, 24, 24, 18, 18, 12, 12, 0])

    def test_formulario_bloqueia_e_sugere_datas(self):
        form = FeriasForm(data={
            "funcionario": self.func.pk, "aquisitivo_inicio": "2025-03-01", "aquisitivo_fim": "2026-02-28",
            "faltas_injustificadas": 0, "inicio": "2026-12-07", "dias": 30, "dias_abono": 0,
        }, empresa=self.emp)
        self.assertTrue(form.is_valid(), form.errors)
        fe = form.save()
        self.assertEqual(fe.data_pagamento, date(2026, 12, 4))  # 2 dias antes, dia útil anterior
        self.assertEqual(fe.data_aviso, date(2026, 11, 7))
        ruim = FeriasForm(data={**form.data, "dias": 3}, empresa=self.emp)
        self.assertFalse(ruim.is_valid())
        self.assertIn("5 dias", str(ruim.non_field_errors()))


class DecimoTerceiroTest(TestCase):
    def setUp(self):
        self.emp = fabrica.empresa()

    def test_avos(self):
        self.assertEqual(c.avos_13(2026, date(2025, 1, 1)), 12)
        self.assertEqual(c.avos_13(2026, date(2026, 3, 17)), 10)  # março tem 15 dias
        self.assertEqual(c.avos_13(2026, date(2026, 3, 18)), 9)
        self.assertEqual(c.avos_13(2026, date(2025, 1, 1), date(2026, 6, 14)), 5)

    def test_primeira_e_segunda_parcela(self):
        fabrica.funcionario(self.emp, salario=D("6000"), data_admissao=date(2026, 3, 17))
        nov = fabrica.competencia(self.emp, mes=11, data_adiantamento_13=date(2026, 11, 27))
        calcular_competencia(nov)
        ad = nov.holerites.get(tipo="adiant13")
        # 9 avos até novembro (mar..nov) -> 6000 * 9/12 / 2
        self.assertEqual(ad.liquido, D("2250.00"))
        self.assertEqual(ad.valor_fgts, D("180.00"))
        self.assertEqual(ad.valor_inss, 0)

        dt = Competencia.objects.create(empresa=self.emp, tipo="13", ano=2026, mes=12,
                                        data_pagamento=date(2026, 12, 18))
        calcular_competencia(dt)
        h = dt.holerites.get(tipo="dec13")
        v = itens(h)
        self.assertEqual(v["5001"], D("5000.00"))  # 10/12 de 6.000
        self.assertEqual(v["9214"], D("2250.00"))
        inss = c.calcular_inss(D("5000"), fabrica_tab())
        self.assertEqual(v["9202"], inss.valor)
        # IRRF exclusivo, sem simplificado: base 4.498,49 -> 336,67 - redução 312,89 = 23,78
        self.assertEqual(v["9205"], D("23.78"))
        self.assertEqual(h.liquido, D("5000") - D("2250") - inss.valor - D("23.78"))
        self.assertEqual(h.base_fgts, D("2750.00"))  # 5001 - 9214

    def test_irrf_13_sem_desconto_simplificado(self):
        r = c.irrf_13(D("10000"), D("988.09"), 0, fabrica_tab())
        self.assertFalse(r.usou_desconto_simplificado)
        self.assertEqual(r.base, D("9011.91"))
        self.assertEqual(r.valor, c.r2(D("9011.91") * D("0.275") - D("908.73")))


class ConformidadeTest(TestCase):
    def test_alertas(self):
        emp = fabrica.empresa()
        f = fabrica.funcionario(emp, salario=D("1000"), data_admissao=date(2024, 1, 10))
        alertas = verificar(emp, hoje=date(2026, 11, 20))
        titulos = " | ".join(a.titulo for a in alertas)
        self.assertIn("Certificado digital não cadastrado", titulos)
        self.assertIn(f"{f.nome}: admissão (S-2200) não enviada", titulos)
        self.assertIn("salário abaixo do mínimo", titulos)
        self.assertIn("férias vencidas", titulos)  # período 2024-2025 sem férias, concessivo até 01/2026
        self.assertIn("1ª parcela do 13º salário não programada", titulos)
        self.assertIn("Folha de 10/2026 não fechada", titulos)
        self.assertEqual(alertas[0].nivel, CRITICO)
        for a in alertas:
            self.assertTrue(a.base_legal)

    def test_quinto_dia_util_e_vencimentos(self):
        self.assertEqual(c.quinto_dia_util(2026, 11), date(2026, 11, 6))
        self.assertEqual(c.vencimento_dia_20(2026, 10), date(2026, 11, 20))
        self.assertEqual(c.vencimento_dia_20(2026, 11), date(2026, 12, 18))  # 20/12/2026 é domingo


def fabrica_tab():
    from folha.tabelas import tabelas_do_ano

    return tabelas_do_ano(2026)
