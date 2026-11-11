"""Relatórios da folha: todos abrem, exportam para Excel e batem com os holerites."""

from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from folha.models import Competencia, Holerite
from folha.relatorios import RELATORIOS
from folha.servico import calcular_competencia


class RelatoriosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("dados_demo", verbosity=0)
        for comp in Competencia.objects.filter(status="aberta"):
            calcular_competencia(comp)
        cls.comp = Competencia.objects.filter(tipo="mensal", holerites__isnull=False).distinct().first()

    def setUp(self):
        self.client.login(username="admin", password="admin")

    def test_central_lista_todos_os_relatorios(self):
        r = self.client.get("/folha/relatorios/")
        self.assertEqual(r.status_code, 200)
        for t in RELATORIOS:
            self.assertContains(r, f"/folha/relatorios/{t.slug}/")

    def test_todos_abrem_e_exportam_para_excel(self):
        for t in RELATORIOS:
            with self.subTest(t.slug):
                r = self.client.get(f"/folha/relatorios/{t.slug}/")
                self.assertEqual(r.status_code, 200)
                r = self.client.get(f"/folha/relatorios/{t.slug}/?formato=csv")
                self.assertEqual(r.status_code, 200)
                self.assertIn("attachment", r["Content-Disposition"])
                self.assertTrue(r.content.startswith("﻿".encode()))

    def test_resumo_bate_com_os_holerites(self):
        hs = Holerite.objects.filter(competencia=self.comp)
        liquido = sum((h.liquido for h in hs), Decimal("0"))
        texto = f"{liquido:.2f}".replace(".", ",")
        r = self.client.get(f"/folha/relatorios/resumo-folha/?competencia={self.comp.pk}&formato=csv")
        self.assertIn(f"Líquido a pagar;{texto}", r.content.decode("utf-8-sig"))

    def test_liquidos_somam_o_total_da_folha(self):
        hs = Holerite.objects.filter(competencia=self.comp)
        total = sum((h.liquido for h in hs), Decimal("0"))
        csv = self.client.get(f"/folha/relatorios/liquidos/?competencia={self.comp.pk}&formato=csv").content
        ultima = [l for l in csv.decode("utf-8-sig").splitlines() if l.startswith(";Total")][0]
        self.assertTrue(ultima.endswith(f"{total:.2f}".replace(".", ",")))

    def test_filtros_invalidos_nao_quebram(self):
        r = self.client.get("/folha/relatorios/ficha-financeira/?ano=abc&mes=99&funcionario=x&competencia=999999")
        self.assertEqual(r.status_code, 200)

    def test_relatorio_inexistente_404(self):
        self.assertEqual(self.client.get("/folha/relatorios/nao-existe/").status_code, 404)

    def test_exige_login(self):
        self.client.logout()
        r = self.client.get("/folha/relatorios/resumo-folha/")
        self.assertEqual(r.status_code, 302)
