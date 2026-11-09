from datetime import date
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from esocial.models import Evento
from folha.models import Competencia, Rubrica
from pessoal.models import Funcionario

from . import fabrica


class TelasTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("contador", password="x")
        self.client.force_login(self.user)

    def test_exige_login(self):
        self.client.logout()
        resp = self.client.get(reverse("pessoal:lista"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp["Location"])

    def test_sem_empresa_redireciona_para_cadastro(self):
        resp = self.client.get(reverse("pessoal:lista"))
        self.assertRedirects(resp, reverse("empresas:nova"))

    def test_fluxo_completo_pelas_telas(self):
        resp = self.client.post(reverse("empresas:nova"), {
            "razao_social": "Mercado Bom Preço LTDA", "tp_insc": 1, "nr_insc": "11.222.333/0001-81",
            "class_trib": "99", "cnae": "4711-3/02", "fpas": "515", "cod_terceiros": "0115", "aliq_terceiros": "5.80",
            "aliq_rat": 2, "fap": "1.0000", "cnpj_sindicato": "11.444.777/0001-61", "inicio_esocial": "2026-01",
            "dia_pagamento": 5, "ambiente_esocial": 2,
        })
        self.assertEqual(resp.status_code, 302, getattr(resp, "context", {}) and resp.context["form"].errors)
        self.client.post(reverse("pessoal:cargos"), {"nome": "Caixa", "cbo": "421125"})
        cargo = self.client.get(reverse("pessoal:cargos")).context["cargos"][0]
        resp = self.client.post(reverse("pessoal:novo"), {
            "matricula": "10", "nome": "Carla Mendes", "cpf": "529.982.247-25", "data_nascimento": "1995-02-03",
            "sexo": "F", "raca_cor": 1, "grau_instrucao": "07", "cep": "01310-100", "logradouro": "Rua A",
            "numero": "10", "cod_municipio": "3550308", "uf": "SP", "data_admissao": "2026-10-16", "categoria": "101",
            "cargo": cargo.pk, "salario": "2400.00", "tipo_contrato": 1, "horas_semanais": "44", "tipo_jornada": 3,
            "descricao_jornada": "Seg a sáb", "insalubridade": 0, "vale_transporte": "0",
        })
        self.assertEqual(resp.status_code, 302, resp.context and resp.context["form"].errors)
        func = Funcionario.objects.get(matricula="10")
        self.assertEqual(func.cpf, "52998224725")

        self.client.post(reverse("esocial:admissao", args=[func.pk]))
        self.assertEqual(Evento.objects.get(tipo="S-2200").status, "pendente")

        self.client.post(reverse("folha:competencia_nova"), {
            "ano": 2026, "mes": 10, "feriados": 0, "data_pagamento": "2026-11-05",
        })
        comp = Competencia.objects.get()
        he = Rubrica.objects.get(empresa=comp.empresa, papel="he50")
        self.client.post(reverse("folha:lancamento_novo", args=[comp.pk]),
                         {"funcionario": func.pk, "rubrica": he.pk, "quantidade": "2"})
        self.client.post(reverse("folha:calcular", args=[comp.pk]))
        hol = comp.holerites.get()
        self.assertEqual(hol.dias_trabalhados, 15)  # admitida em 16/10
        self.assertContains(self.client.get(reverse("folha:competencia", args=[comp.pk])), "Prévia da DCTFWeb")
        self.assertContains(self.client.get(reverse("folha:holerite", args=[hol.pk])), "Carla Mendes")

        self.client.post(reverse("folha:fechar", args=[comp.pk]), {"transmitir_dctfweb": "on"})
        self.assertEqual(set(Evento.objects.filter(competencia=comp).values_list("status", flat=True)), {"pendente"})
        resp = self.client.get(reverse("esocial:eventos"))
        self.assertContains(resp, "S-1299")
        ev = Evento.objects.get(tipo="S-1299")
        self.assertContains(self.client.get(reverse("esocial:evento", args=[ev.pk])), "evtFechaEvPer")

    def test_paginas_principais_carregam(self):
        call_command("dados_demo", stdout=open("/dev/null", "w"))
        comp = Competencia.objects.get()
        func = Funcionario.objects.first()
        urls = [
            reverse("dashboard"), reverse("empresas:lista"), reverse("pessoal:lista"), reverse("pessoal:cargos"),
            reverse("pessoal:detalhe", args=[func.pk]), reverse("pessoal:editar", args=[func.pk]),
            reverse("pessoal:novo"), reverse("folha:rubricas"), reverse("folha:competencias"),
            reverse("folha:competencia", args=[comp.pk]), reverse("folha:holerites_impressao", args=[comp.pk]),
            reverse("esocial:eventos"), reverse("esocial:lotes"), reverse("esocial:guia"),
            reverse("empresas:certificado", args=[comp.empresa.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_isolamento_entre_empresas(self):
        a = fabrica.empresa()
        b = fabrica.empresa(nr_insc="12.ABC.345/01DE-35", razao_social="Outra")
        func_b = fabrica.funcionario(b)
        session = self.client.session
        session["empresa_id"] = a.pk
        session.save()
        self.assertEqual(self.client.get(reverse("pessoal:detalhe", args=[func_b.pk])).status_code, 404)
