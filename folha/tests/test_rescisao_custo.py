from datetime import date
from decimal import Decimal as D

from django.test import TestCase

from esocial.servico import gerar_desligamento
from folha.custo import custo_mensal
from folha.models import Rescisao
from folha.rescisao import calcular_rescisao, problemas_rescisao

from . import fabrica


def valores(resc):
    return {i["codigo"]: D(i["valor"]) for i in resc.itens}


class RescisaoTest(TestCase):
    def setUp(self):
        self.emp = fabrica.empresa()
        self.func = fabrica.funcionario(self.emp)  # R$ 3.000, admitida em 01/03/2025, sem dependentes

    def rescisao(self, **kw):
        dados = dict(funcionario=self.func, motivo="02", tipo_aviso="indenizado", data_aviso=date(2026, 11, 20),
                     data_desligamento=date(2026, 11, 20), data_pagamento=date(2026, 11, 27), saldo_fgts=D("2000"))
        dados.update(kw)
        return calcular_rescisao(Rescisao.objects.create(**dados))

    def test_dispensa_sem_justa_causa(self):
        r = self.rescisao()
        v = valores(r)
        self.assertEqual(r.dias_aviso, 33)  # 30 + 3 por 1 ano completo (Lei 12.506)
        self.assertEqual(r.data_projetada, date(2026, 12, 23))
        self.assertEqual(v["6003"], D("3300.00"))  # aviso indenizado
        self.assertEqual(v["6000"], D("2000.00"))  # 20 dias de saldo
        self.assertEqual(v["6002"], D("2750.00"))  # 11/12 de 13º
        self.assertEqual(v["6001"], D("250.00"))  # +1/12 pela projeção do aviso
        self.assertEqual(v["6007"], D("4000.00"))  # período 03/2025-02/2026 + 1/3
        self.assertEqual(v["6006"], D("3333.33"))  # 10/12 + 1/3
        self.assertEqual(r.total_proventos, D("15633.33"))
        self.assertEqual(v["9201"], D("155.69"))  # INSS só sobre o saldo
        self.assertEqual(v["9202"], D("248.60"))  # INSS do 13º em separado
        self.assertNotIn("9203", v)
        self.assertEqual(r.liquido, D("15229.04"))
        self.assertEqual(r.fgts_rescisorio, D("664.00"))  # 8% de saldo + 13º + aviso
        self.assertEqual(r.multa_fgts, D("1065.60"))  # 40% de (2.000 + 664)
        self.func.refresh_from_db()
        self.assertEqual(self.func.data_desligamento, date(2026, 11, 20))
        self.assertTrue(self.func.aviso_previo_indenizado)

    def test_justa_causa_perde_proporcionais(self):
        r = self.rescisao(motivo="01", tipo_aviso="nenhum")
        v = valores(r)
        self.assertEqual(set(v) - {"9201"}, {"6000", "6007"})  # saldo e férias vencidas
        self.assertEqual(r.multa_fgts, 0)

    def test_pedido_de_demissao_sem_cumprir_aviso(self):
        r = self.rescisao(motivo="07", tipo_aviso="nao_cumprido")
        v = valores(r)
        self.assertNotIn("6003", v)
        self.assertEqual(v["9299"], D("3000.00"))  # desconta 30 dias (CLT art. 487, §2º)
        self.assertEqual(r.multa_fgts, 0)
        self.assertEqual(r.dias_aviso, 30)

    def test_acordo_484a(self):
        r = self.rescisao(motivo="33")
        v = valores(r)
        self.assertEqual(v["6003"], D("1650.00"))  # metade de 33 dias = 16,5 dias
        self.assertEqual(r.multa_fgts, (D("2000") + r.fgts_rescisorio) * D("0.20"))

    def test_prazo_de_pagamento(self):
        r = self.rescisao(data_pagamento=date(2026, 12, 5))
        self.assertIn("Pagamento fora do prazo", [p[0] for p in problemas_rescisao(r)])

    def test_s2299_com_verbas_valido_no_xsd(self):
        r = self.rescisao()
        ev = gerar_desligamento(self.func)
        self.assertEqual(ev.status, "pendente", ev.mensagens)
        self.assertIn("<verbasResc>", ev.xml)
        self.assertIn("<codRubr>6003</codRubr>", ev.xml)
        self.assertIn("<dtProjFimAPI>2026-12-23</dtProjFimAPI>", ev.xml)
        self.assertIn("S-1010:6003", ev.depende)
        self.assertEqual(r.ide_dm_dev, "RE2026110001")


class CustoTest(TestCase):
    def test_custo_lucro_presumido(self):
        emp = fabrica.empresa()  # RAT 1%, FAP 1, terceiros 5,8%
        custo = custo_mensal(emp, D("3000"), vale_transporte=D("220"), beneficios=D("500"))
        self.assertEqual(custo.total_grupo("encargos"), D("804.00"))  # 26,8%
        self.assertEqual(custo.total_grupo("fgts"), D("240.00"))
        # 13º 250 + férias 333,33 + (583,33 x 34,8%) 203,00 + multa 40% x 8% x 3.583,33 = 114,67
        self.assertEqual(custo.total_grupo("provisoes"), D("901.00"))
        self.assertEqual(custo.total_grupo("beneficios"), D("540.00"))  # VT 220-180=40 + 500
        self.assertEqual(custo.total, D("5485.00"))
        self.assertEqual(custo.multiplicador, D("1.83"))

    def test_custo_simples_nacional(self):
        emp = fabrica.empresa(nr_insc="12.ABC.345/01DE-35", class_trib="01")
        custo = custo_mensal(emp, D("3000"))
        self.assertEqual(custo.total_grupo("encargos"), 0)  # CPP dentro do DAS
        self.assertEqual(custo.total_grupo("fgts"), D("240.00"))
