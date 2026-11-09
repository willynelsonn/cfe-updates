from datetime import date
from decimal import Decimal as D
from unittest import mock

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from lxml import etree

from esocial import xml_eventos as xe
from esocial.assinatura import ErroCertificado, assinar, carregar_pfx
from esocial.models import Evento, Lote
from esocial.servico import (
    ErroESocial,
    consultar_lotes_enviados,
    fechar_competencia,
    gerar_ferias,
    processar_fila,
    gerar_admissao,
    gerar_desligamento,
    gerar_eventos_iniciais,
    transmitir_pendentes,
)
from esocial.validacao import validar_evento, validar_lote
from esocial.webservice import (
    envelope_consulta,
    envelope_envio,
    ler_retorno_consulta,
    ler_retorno_envio,
    montar_lote,
)
from folha.models import Competencia, Ferias, Lancamento, Rubrica
from folha.servico import calcular_competencia, calcular_ferias
from folha.tests import fabrica

from .certificado_teste import gerar_pfx, verificar_assinatura


def _sem_erros(testcase, eventos):
    for ev in eventos:
        testcase.assertEqual(ev.status, "pendente", f"{ev.tipo} {ev.descricao}: {ev.mensagens}")


class GeracaoEventosTest(TestCase):
    def setUp(self):
        self.emp = fabrica.empresa()
        self.func = fabrica.funcionario(self.emp)
        fabrica.filho(self.func)

    def test_eventos_iniciais_validos_no_xsd(self):
        eventos = gerar_eventos_iniciais(self.emp)
        tipos = [e.tipo for e in eventos]
        self.assertEqual(tipos[:3], ["S-1000", "S-1005", "S-1020"])
        self.assertEqual(tipos.count("S-1010"), Rubrica.objects.filter(empresa=self.emp).count())
        _sem_erros(self, eventos)

    def test_empresa_simples_nacional(self):
        emp = fabrica.empresa(nr_insc="12.ABC.345/01DE-35", class_trib="01", razao_social="Loja Alfa")
        _sem_erros(self, gerar_eventos_iniciais(emp))  # inclui CNPJ alfanumérico

    def test_admissao_valida(self):
        ev = gerar_admissao(self.func)
        _sem_erros(self, [ev])
        self.assertIn("<cpfTrab>52998224725</cpfTrab>", ev.xml)
        self.assertIn("<nrInsc>11222333</nrInsc>", ev.xml)  # raiz do CNPJ

    def test_desligamento_valido(self):
        self.func.data_desligamento = date(2026, 10, 20)
        self.func.motivo_desligamento = "02"
        self.func.aviso_previo_indenizado = True
        self.func.save()
        ev = gerar_desligamento(self.func)
        _sem_erros(self, [ev])
        self.assertIn("<dtProjFimAPI>2026-11-22</dtProjFimAPI>", ev.xml)  # 33 dias de aviso

    def test_fechamento_folha_regime_de_caixa(self):
        # Outubro: salário pago em 05/11 -> S-1210 só no fechamento de novembro.
        out = fabrica.competencia(self.emp)
        he = Rubrica.objects.get(empresa=self.emp, papel="he50")
        Lancamento.objects.create(competencia=out, funcionario=self.func, rubrica=he, quantidade=D("5"))
        calcular_competencia(out)
        eventos = fechar_competencia(out, transmitir_dctfweb=True)
        _sem_erros(self, eventos)
        self.assertEqual([e.tipo for e in eventos], ["S-1200", "S-1299"])
        self.assertIn("<evtPgtos>N</evtPgtos>", eventos[-1].xml)
        self.assertIn("<transDCTFWeb>S</transDCTFWeb>", eventos[-1].xml)
        self.assertIn("S-2200:func:", " ".join(eventos[0].depende))
        self.assertIn("S-1010:1010", eventos[0].depende)
        out.refresh_from_db()
        self.assertEqual(out.status, "fechada")

        nov = fabrica.competencia(self.emp, mes=11, data_pagamento=date(2026, 12, 4),
                                  data_adiantamento_13=date(2026, 11, 27))
        calcular_competencia(nov)
        eventos = fechar_competencia(nov)
        _sem_erros(self, eventos)
        self.assertEqual([e.tipo for e in eventos], ["S-1200", "S-1210", "S-1299"])
        s1200, s1210, s1299 = eventos
        self.assertEqual(s1200.xml.count("<dmDev>"), 2)  # folha + 1ª parcela do 13º
        self.assertIn("<codRubr>5504</codRubr>", s1200.xml)
        self.assertEqual(s1210.per_apur, "2026-11")
        self.assertIn("<perRef>2026-10</perRef>", s1210.xml)  # salário de outubro
        self.assertIn("<perRef>2026-11</perRef>", s1210.xml)  # adiantamento do 13º
        self.assertIn("<evtPgtos>S</evtPgtos>", s1299.xml)
        self.assertEqual(sorted(s1210.depende), sorted([
            f"S-1200:2026-10:func:{self.func.pk}", f"S-1200:2026-11:func:{self.func.pk}"]))

    def test_nao_fecha_com_pagamentos_de_folha_aberta(self):
        out = fabrica.competencia(self.emp)
        calcular_competencia(out)  # calculada, não fechada
        nov = fabrica.competencia(self.emp, mes=11, data_pagamento=date(2026, 12, 4))
        calcular_competencia(nov)
        with self.assertRaisesMessage(ErroESocial, "Feche essas folhas primeiro"):
            fechar_competencia(nov)

    def test_decimo_terceiro_anual(self):
        fabrica.funcionario(self.emp, matricula="0009", nome="Gerente", cpf="111.444.777-35", salario=D("9000"))
        nov = fabrica.competencia(self.emp, mes=11, data_pagamento=date(2026, 12, 4),
                                  data_adiantamento_13=date(2026, 11, 27))
        calcular_competencia(nov)
        dt = Competencia.objects.create(empresa=self.emp, tipo="13", ano=2026, mes=12,
                                        data_pagamento=date(2026, 12, 18))
        calcular_competencia(dt)
        eventos = fechar_competencia(dt)
        _sem_erros(self, eventos)
        self.assertEqual([e.tipo for e in eventos], ["S-1200", "S-1200", "S-1299"])
        maria = next(e for e in eventos if e.funcionario == self.func)
        self.assertIn("<indApuracao>2</indApuracao>", maria.xml)
        self.assertIn("<perApur>2026</perApur>", maria.xml)
        for cod in ("5001", "9214", "9202"):
            self.assertIn(f"<codRubr>{cod}</codRubr>", maria.xml)
        self.assertNotIn("<codRubr>9205</codRubr>", maria.xml)  # 13º de R$ 3.000: isento em 2026
        gerente = next(e for e in eventos if e.tipo == "S-1200" and e.funcionario != self.func)
        self.assertIn("<codRubr>9205</codRubr>", gerente.xml)

    def test_ferias_s2230(self):
        fe = Ferias.objects.create(
            funcionario=self.func, aquisitivo_inicio=date(2025, 3, 1), aquisitivo_fim=date(2026, 2, 28),
            inicio=date(2026, 11, 3), dias=30, data_pagamento=date(2026, 10, 30), data_aviso=date(2026, 10, 1))
        calcular_ferias(fe)
        ev = gerar_ferias(fe)
        _sem_erros(self, [ev])
        self.assertIn("<codMotAfast>15</codMotAfast>", ev.xml)
        self.assertIn("<dtTermAfast>2026-12-02</dtTermAfast>", ev.xml)

    def test_id_do_evento(self):
        id_evento = xe.gerar_id(self.emp)
        self.assertRegex(id_evento, r"^ID111222333000000\d{19}$")
        self.assertEqual(len(id_evento), 36)


class AssinaturaTest(TestCase):
    def setUp(self):
        self.emp = fabrica.empresa()
        self.cert = carregar_pfx(gerar_pfx("segredo"), "segredo")

    def test_assinatura_valida_e_aceita_pelo_xsd(self):
        _, root = xe.s1000(self.emp)
        assinado = assinar(root, self.cert)
        xml = etree.tostring(assinado)
        self.assertEqual(validar_evento("S-1000", xml), [])
        ref = assinado.find(".//{http://www.w3.org/2000/09/xmldsig#}Reference")
        self.assertEqual(ref.get("URI"), "")
        verificar_assinatura(xml)  # levanta exceção se inválida

    def test_lote_valido(self):
        eventos = []
        for rub in Rubrica.objects.filter(empresa=self.emp)[:3]:
            id_evento, root = xe.s1010(self.emp, rub)
            eventos.append((id_evento, assinar(root, self.cert)))
        lote = montar_lote(1, self.emp, eventos)
        self.assertEqual(validar_lote(lote), [])
        envelope = envelope_envio(lote)
        self.assertIn(b"EnviarLoteEventos", envelope)
        self.assertIn(b"protocoloEnvio", envelope_consulta("1.2.202611.0000000000000000001"))

    def test_senha_errada(self):
        with self.assertRaises(ErroCertificado):
            carregar_pfx(gerar_pfx("certa"), "errada")

    def test_certificado_vencido(self):
        vencido = carregar_pfx(gerar_pfx("x", dias=-2), "x")
        _, root = xe.s1000(self.emp)
        with self.assertRaises(ErroCertificado):
            assinar(root, vencido)


RETORNO_ENVIO = b"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>
<EnviarLoteEventosResponse xmlns="http://www.esocial.gov.br/servicos/empregador/lote/eventos/envio/v1_1_0">
<EnviarLoteEventosResult><eSocial xmlns="http://www.esocial.gov.br/schema/lote/eventos/envio/retornoEnvio/v1_1_0">
<retornoEnvioLoteEventos><ideEmpregador><tpInsc>1</tpInsc><nrInsc>11222333</nrInsc></ideEmpregador>
<status><cdResposta>201</cdResposta><descResposta>Lote Recebido com Sucesso.</descResposta></status>
<dadosRecepcaoLote><dhRecepcao>2026-11-09T10:00:00</dhRecepcao><versaoAplicativoRecepcao>1</versaoAplicativoRecepcao>
<protocoloEnvio>1.2.202611.0000000000000000001</protocoloEnvio></dadosRecepcaoLote>
</retornoEnvioLoteEventos></eSocial></EnviarLoteEventosResult></EnviarLoteEventosResponse></s:Body></s:Envelope>"""

RETORNO_CONSULTA_UM = """<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>
<ConsultarLoteEventosResponse><ConsultarLoteEventosResult><eSocial xmlns="http://www.esocial.gov.br/schema/lote/eventos/envio/retornoProcessamento/v1_3_0">
<retornoProcessamentoLoteEventos><status><cdResposta>201</cdResposta><descResposta>Lote processado com sucesso.</descResposta></status>
<retornoEventos><evento Id="{ok}"><retornoEvento><eSocial xmlns="http://www.esocial.gov.br/schema/evt/retornoEvento/v1_2_1"><retornoEvento>
<processamento><cdResposta>201</cdResposta><descResposta>Sucesso.</descResposta></processamento>
<recibo><nrRecibo>1.1.0000000000000000001</nrRecibo></recibo></retornoEvento></eSocial></retornoEvento></evento>
</retornoEventos></retornoProcessamentoLoteEventos></eSocial></ConsultarLoteEventosResult></ConsultarLoteEventosResponse></s:Body></s:Envelope>"""

RETORNO_CONSULTA = """<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>
<ConsultarLoteEventosResponse><ConsultarLoteEventosResult><eSocial xmlns="http://www.esocial.gov.br/schema/lote/eventos/envio/retornoProcessamento/v1_3_0">
<retornoProcessamentoLoteEventos><status><cdResposta>201</cdResposta><descResposta>Lote processado com sucesso.</descResposta></status>
<retornoEventos>
<evento Id="{ok}"><retornoEvento><eSocial xmlns="http://www.esocial.gov.br/schema/evt/retornoEvento/v1_2_1"><retornoEvento>
<processamento><cdResposta>201</cdResposta><descResposta>Sucesso.</descResposta></processamento>
<recibo><nrRecibo>1.1.0000000000000000001</nrRecibo></recibo></retornoEvento></eSocial></retornoEvento></evento>
<evento Id="{erro}"><retornoEvento><eSocial xmlns="http://www.esocial.gov.br/schema/evt/retornoEvento/v1_2_1"><retornoEvento>
<processamento><cdResposta>401</cdResposta><descResposta>Lote processado com erros.</descResposta>
<ocorrencias><ocorrencia><tipo>1</tipo><codigo>1030</codigo><descricao>CPF inexistente.</descricao><localizacao>cpfTrab</localizacao></ocorrencia></ocorrencias>
</processamento></retornoEvento></eSocial></retornoEvento></evento>
</retornoEventos></retornoProcessamentoLoteEventos></eSocial></ConsultarLoteEventosResult></ConsultarLoteEventosResponse></s:Body></s:Envelope>"""


@override_settings(PRIVATE_MEDIA_ROOT="/tmp/folhaweb-testes-media")
class TransmissaoTest(TestCase):
    """Fluxo completo com o webservice simulado (mock)."""

    def setUp(self):
        self.emp = fabrica.empresa()
        self.emp.certificado.save("teste.pfx", ContentFile(gerar_pfx("1234")), save=False)
        self.emp.definir_senha_certificado("1234")
        self.emp.save()

    def test_fila_respeita_dependencias(self):
        eventos = gerar_eventos_iniciais(self.emp)[:2]  # S-1000 e S-1005
        Evento.objects.exclude(pk__in=[e.pk for e in eventos]).delete()
        s1000, s1005 = eventos
        with mock.patch("esocial.webservice._post", return_value=RETORNO_ENVIO) as post:
            lotes = transmitir_pendentes(self.emp)
        self.assertEqual(len(lotes), 1)
        self.assertEqual(lotes[0].protocolo, "1.2.202611.0000000000000000001")
        enviado = post.call_args.args[2]
        self.assertIn(b"<Signature", enviado)
        self.assertIn(s1000.id_evento.encode(), enviado)
        self.assertNotIn(s1005.id_evento.encode(), enviado)  # espera o S-1000 ser aceito
        s1005.refresh_from_db()
        self.assertEqual(s1005.status, "pendente")
        self.assertIn("Aguardando aceite de: S-1000", s1005.mensagens[0])

        # Governo aceita o S-1000; o próximo passo da fila envia o S-1005 sozinho.
        consulta = RETORNO_CONSULTA_UM.format(ok=s1000.id_evento).encode()
        with mock.patch("esocial.webservice._post", side_effect=[consulta, RETORNO_ENVIO]) as post:
            resultado = processar_fila(self.emp)
        self.assertEqual(resultado["lotes_enviados"], 1)
        s1000.refresh_from_db()
        s1005.refresh_from_db()
        self.assertEqual(s1000.status, "aceito")
        self.assertEqual(s1000.recibo, "1.1.0000000000000000001")
        self.assertEqual(s1005.status, "enviado")

    def test_rejeicao(self):
        ev = gerar_eventos_iniciais(self.emp)[0]
        Evento.objects.exclude(pk=ev.pk).delete()
        with mock.patch("esocial.webservice._post", return_value=RETORNO_ENVIO):
            transmitir_pendentes(self.emp)
        resposta = RETORNO_CONSULTA.format(ok="OUTRO", erro=ev.id_evento).encode()
        with mock.patch("esocial.webservice._post", return_value=resposta):
            consultar_lotes_enviados(self.emp)
        ev.refresh_from_db()
        self.assertEqual(ev.status, "rejeitado")
        self.assertIn("[1030] CPF inexistente. (cpfTrab)", ev.mensagens)
        self.assertEqual(Lote.objects.get().status, "processado")

    def test_leitura_retornos(self):
        r = ler_retorno_envio(RETORNO_ENVIO)
        self.assertTrue(r.aceito)
        c = ler_retorno_consulta(RETORNO_CONSULTA.format(ok="A", erro="B").encode())
        self.assertFalse(c.em_processamento)
        self.assertEqual(len(c.eventos), 2)
