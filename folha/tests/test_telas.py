from datetime import date

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from esocial.models import Evento
from folha.models import Competencia, Ferias, Rubrica
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
            "descricao_jornada": "Seg a sáb", "insalubridade": 0, "vale_transporte": "0", "beneficios_mensais": "0",
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
        self.assertContains(self.client.get(reverse("folha:competencia", args=[comp.pk])), "Prévia do DARF")
        self.assertContains(self.client.get(reverse("folha:holerite", args=[hol.pk])), "Carla Mendes")

        self.client.post(reverse("folha:fechar", args=[comp.pk]), {"transmitir_dctfweb": "on"})
        self.assertEqual(set(Evento.objects.filter(competencia=comp).values_list("status", flat=True)), {"pendente"})
        resp = self.client.get(reverse("esocial:eventos"))
        self.assertContains(resp, "S-1299")
        ev = Evento.objects.get(tipo="S-1299")
        self.assertContains(self.client.get(reverse("esocial:evento", args=[ev.pk])), "evtFechaEvPer")

    def test_paginas_principais_carregam(self):
        call_command("dados_demo", stdout=open("/dev/null", "w"))
        comp = Competencia.objects.get(mes=10)
        func = Funcionario.objects.first()
        ferias = Ferias.objects.first()
        urls = [
            reverse("dashboard"), reverse("empresas:lista"), reverse("pessoal:lista"), reverse("pessoal:cargos"),
            reverse("pessoal:detalhe", args=[func.pk]), reverse("pessoal:editar", args=[func.pk]),
            reverse("pessoal:novo"), reverse("folha:rubricas"), reverse("folha:competencias"),
            reverse("folha:competencia", args=[comp.pk]), reverse("folha:holerites_impressao", args=[comp.pk]),
            reverse("esocial:eventos"), reverse("esocial:lotes"), reverse("esocial:guia"),
            reverse("empresas:certificado", args=[comp.empresa.pk]), reverse("folha:guias", args=[comp.pk]),
            reverse("folha:ferias"), reverse("folha:ferias_nova"), reverse("folha:ferias_detalhe", args=[ferias.pk]),
            reverse("folha:decimo_terceiro"), reverse("folha:competencia_editar", args=[comp.pk]),
            reverse("folha:holerite", args=[comp.holerites.first().pk]),
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


class AutomacaoTest(TestCase):
    def setUp(self):
        from unittest import mock

        from django.core.files.base import ContentFile

        from esocial.tests.certificado_teste import gerar_pfx

        self.user = get_user_model().objects.create_user("dp", password="x")
        self.client.force_login(self.user)
        self.emp = fabrica.empresa()
        self.emp.certificado.save("t.pfx", ContentFile(gerar_pfx("1")), save=False)
        self.emp.definir_senha_certificado("1")
        self.emp.save()
        self.post = mock.patch("esocial.webservice._post", side_effect=self._resposta).start()
        self.addCleanup(mock.patch.stopall)

    def _resposta(self, url, action, corpo, cert):
        from esocial.tests.test_eventos import RETORNO_ENVIO

        return RETORNO_ENVIO

    def test_admissao_vai_sozinha_para_a_fila(self):
        cargo = self.emp.cargos.create(nome="Caixa", cbo="421125")
        self.client.post(reverse("pessoal:novo"), {
            "matricula": "7", "nome": "Paulo Lima", "cpf": "111.444.777-35", "data_nascimento": "1990-01-01",
            "sexo": "M", "raca_cor": 1, "grau_instrucao": "07", "cep": "01310100", "logradouro": "Rua B",
            "numero": "1", "cod_municipio": "3550308", "uf": "SP", "data_admissao": "2026-12-01", "categoria": "101",
            "cargo": cargo.pk, "salario": "2000", "tipo_contrato": 1, "horas_semanais": "44", "tipo_jornada": 3,
            "descricao_jornada": "Seg a sex", "insalubridade": 0, "vale_transporte": "0", "beneficios_mensais": "0",
        })
        ev = Evento.objects.get(tipo="S-2200")
        self.assertIn("S-1000", ev.depende)
        # A fila foi processada: o S-1000 (gerado automaticamente) já foi enviado; o S-2200 espera.
        self.assertTrue(self.post.called)
        self.assertEqual(Evento.objects.get(tipo="S-1000").status, "enviado")
        self.assertEqual(ev.status, "pendente")

    def test_apurar_calcula_fecha_e_envia(self):
        fabrica.funcionario(self.emp, esocial_ja_cadastrado=True)
        self.emp.esocial_ja_iniciado = True
        self.emp.save()
        comp = fabrica.competencia(self.emp)
        resp = self.client.post(reverse("folha:apurar", args=[comp.pk]), {"transmitir_dctfweb": "1"})
        self.assertRedirects(resp, reverse("folha:competencia", args=[comp.pk]))
        comp.refresh_from_db()
        self.assertEqual(comp.status, "fechada")
        tipos = set(Evento.objects.values_list("tipo", flat=True))
        self.assertTrue({"S-1200", "S-1299", "S-1010"} <= tipos)
        self.assertNotIn("S-1000", tipos)  # empresa já iniciada por outro sistema
        self.assertEqual(Evento.objects.filter(tipo="S-1010", status="enviado").count(),
                         Rubrica.objects.filter(empresa=self.emp).count())
        self.assertEqual(Evento.objects.get(tipo="S-1200").status, "pendente")  # espera as rubricas
        self.assertEqual(comp.guias.count(), 2)
        resp = self.client.get(reverse("folha:guias", args=[comp.pk]))
        self.assertContains(resp, "DARF DCTFWeb")
        self.assertContains(resp, "Prevista (aguardando eSocial)")

    def test_guias_ficam_prontas_quando_s1299_aceito(self):
        from folha.guias import atualizar_guias, emitir_darf

        fabrica.funcionario(self.emp)
        comp = fabrica.competencia(self.emp)
        self.client.post(reverse("folha:calcular", args=[comp.pk]))
        self.client.post(reverse("folha:fechar", args=[comp.pk]), {"transmitir_dctfweb": "on"})
        Evento.objects.filter(tipo="S-1299").update(status="aceito")
        darf, fgts = atualizar_guias(comp)
        self.assertEqual((darf.status, fgts.status), ("disponivel", "disponivel"))
        self.assertEqual(darf.vencimento, date(2026, 11, 20))
        emitir_darf(darf)
        self.assertIn("e-CAC", darf.mensagem)  # sem Integra Contador contratado

    def test_darf_pelo_integra_contador(self):
        import base64
        import json
        from unittest import mock

        from django.test import override_settings

        from folha.guias import atualizar_guias, emitir_darf

        fabrica.funcionario(self.emp)
        comp = fabrica.competencia(self.emp)
        self.client.post(reverse("folha:calcular", args=[comp.pk]))
        self.client.post(reverse("folha:fechar", args=[comp.pk]))
        Evento.objects.filter(tipo="S-1299").update(status="aceito")
        darf = atualizar_guias(comp)[0]
        cfg = {"key": "k", "secret": "s", "contratante": "11222333000181", "servico_darf": "GERARGUIA31",
               "url_autenticacao": "https://auth.exemplo", "url_api": "https://api.exemplo/v1"}
        auth = mock.Mock(status_code=200, json=lambda: {"access_token": "a", "jwt_token": "j"})
        pdf = base64.b64encode(b"%PDF-1.4 darf").decode()
        api = mock.Mock(status_code=200, json=lambda: {"dados": json.dumps({"PDFByteArrayBase64": pdf}),
                                                       "mensagens": []})
        with override_settings(INTEGRA_CONTADOR=cfg), mock.patch("requests.post", side_effect=[auth, api]) as post:
            emitir_darf(darf)
        corpo = post.call_args_list[1].kwargs["json"]
        self.assertEqual(corpo["pedidoDados"]["idServico"], "GERARGUIA31")
        self.assertEqual(json.loads(corpo["pedidoDados"]["dados"]),
                         {"categoria": "GERAL_MENSAL", "anoPA": "2026", "mesPA": "10"})
        self.assertEqual(darf.status, "emitida")
        self.assertEqual(self.client.get(reverse("folha:guia_pdf", args=[darf.pk])).content, b"%PDF-1.4 darf")

    def test_telas_de_ferias_e_13(self):
        f = fabrica.funcionario(self.emp)
        resp = self.client.get(reverse("folha:ferias_nova") + f"?funcionario={f.pk}")
        self.assertContains(resp, 'value="2025-03-01"')  # período aquisitivo sugerido
        resp = self.client.post(reverse("folha:ferias_nova"), {
            "funcionario": f.pk, "aquisitivo_inicio": "2025-03-01", "aquisitivo_fim": "2026-02-28",
            "faltas_injustificadas": 0, "inicio": "2026-12-07", "dias": 20, "dias_abono": 10,
        })
        fe = Ferias.objects.get()
        self.assertRedirects(resp, reverse("folha:ferias_detalhe", args=[fe.pk]))
        self.assertEqual(Evento.objects.get(tipo="S-2230").ferias, fe)
        for doc in ("aviso", "recibo"):
            self.assertContains(self.client.get(reverse("folha:ferias_documento", args=[fe.pk, doc])), f.nome)
        self.assertContains(self.client.get(reverse("folha:decimo_terceiro") + "?ano=2026"), "Abrir 13º de 2026")
        resp = self.client.post(reverse("folha:decimo_terceiro") + "?ano=2026")
        comp = Competencia.objects.get(tipo="13")
        self.assertRedirects(resp, reverse("folha:competencia", args=[comp.pk]))
        self.assertEqual(comp.data_pagamento, date(2026, 12, 18))

    def test_situacao_json(self):
        dados = self.client.get(reverse("esocial:situacao_json")).json()
        self.assertEqual(set(dados), {"pendentes", "enviados", "aceitos", "problemas", "lotes_aguardando"})
        self.assertIn("lotes_enviados", self.client.post(reverse("esocial:processar_json")).json())


class LoginTest(TestCase):
    def test_logado_em_entrar_vai_para_o_painel(self):
        self.client.force_login(get_user_model().objects.create_user("x", password="x"))
        self.assertRedirects(self.client.get(reverse("login")), reverse("dashboard"), fetch_redirect_response=False)

    def test_seletor_de_cores_no_menu_da_conta(self):
        self.client.force_login(get_user_model().objects.create_user("y", password="y"))
        fabrica.empresa()
        resp = self.client.get(reverse("dashboard"))
        for cor in ("laranja", "azul", "verde", "roxo", "rosa", "grafite"):
            self.assertContains(resp, f'data-cor="{cor}"')
        self.assertContains(resp, 'data-aparencia="auto"')


class AparenciaPadraoTest(TestCase):
    def test_grafite_e_padrao_e_estaticos_versionados(self):
        resp = self.client.get(reverse("login"))
        self.assertContains(resp, '<html lang="pt-br" data-cor="grafite">')
        self.assertRegex(resp.content.decode(), r'js/app\.js\?v=\d+')
