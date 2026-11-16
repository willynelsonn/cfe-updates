"""Exportar e importar funcionários por planilha. Só dados inventados: o repositório é público."""

import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from esocial.models import Evento
from esocial.servico import gerar_admissao
from folha.tests import fabrica
from pessoal.models import Funcionario

CABECALHO = ["matricula", "Nome", "CPF", "Data de nascimento", "Sexo", "CEP", "Logradouro",
             "Código IBGE do município", "UF", "Data de admissão", "Cargo", "Salário mensal"]
NOVA = ["0002", "Ana Teste", "123.456.789-09", "15/08/1995", "Feminino", "1310100", "Rua Exemplo",
        "3550308", "SP", "01/09/2026", "padeiro", "2.500,00"]


def csv_arquivo(*linhas, nome="funcionarios.csv"):
    texto = "\n".join(";".join(l) for l in linhas)
    return SimpleUploadedFile(nome, texto.encode("utf-8-sig"), content_type="text/csv")


class PlanilhaFuncionariosTest(TestCase):
    def setUp(self):
        self.emp = fabrica.empresa(envio_automatico=True)
        self.maria = fabrica.funcionario(self.emp)
        self.user = get_user_model().objects.create_user("escritorio", password="x", is_staff=True)
        self.client.force_login(self.user)
        self.ativar(self.emp)
        self.url = reverse("pessoal:importar")

    def ativar(self, emp):
        sessao = self.client.session
        sessao["empresa_id"] = emp.pk
        sessao.save()

    def enviar(self, arquivo, **extra):
        return self.client.post(self.url, {"arquivo": arquivo, **extra})

    def confirmar(self):
        return self.client.post(self.url, {"confirmar": "1"})

    def test_exporta_xlsx_e_csv_so_da_empresa_ativa(self):
        self.maria.complemento = "=2+3"  # texto que o Excel executaria como fórmula
        self.maria.save()
        outra = fabrica.empresa(razao_social="Outra LTDA", nr_insc="11.444.777/0001-61")
        fabrica.funcionario(outra, nome="Pessoa De Outra Empresa", cpf="111.444.777-35")
        resp = self.client.get(reverse("pessoal:exportar"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment", resp["Content-Disposition"])
        linhas = list(load_workbook(io.BytesIO(resp.content)).active.iter_rows(values_only=True))
        self.assertIn("CPF", linhas[0])
        self.assertEqual(len(linhas), 2)
        self.assertIn("Maria da Silva", linhas[1])
        self.assertIn("529.982.247-25", linhas[1])
        self.assertIn("Padeiro", linhas[1])
        self.assertIn("'=2+3", linhas[1])

        texto = self.client.get(reverse("pessoal:exportar"), {"formato": "csv"}).content.decode("utf-8-sig")
        self.assertIn("Matrícula;Nome;CPF", texto)
        self.assertIn("529.982.247-25", texto)
        self.assertIn("3000,00", texto)
        self.assertIn("01/03/2025", texto)
        self.assertIn(";'=2+3;", texto)
        self.assertNotIn("Outra Empresa", texto)

    def test_importa_novo_com_previa_e_sem_mandar_ao_esocial(self):
        resp = self.enviar(csv_arquivo(CABECALHO, NOVA), ja_no_esocial="on")
        self.assertContains(resp, "Cadastrar")
        self.assertContains(resp, "Confirmar e gravar")
        self.assertFalse(Funcionario.objects.filter(cpf="12345678909").exists())  # prévia não grava

        resp = self.confirmar()
        self.assertRedirects(resp, reverse("pessoal:lista"))
        ana = Funcionario.objects.get(empresa=self.emp, cpf="12345678909")
        self.assertEqual(ana.salario, Decimal("2500.00"))
        self.assertEqual(ana.cep, "01310100")  # zero da frente devolvido
        self.assertEqual(ana.sexo, "F")
        self.assertEqual(ana.cargo, self.maria.cargo)
        self.assertTrue(ana.esocial_ja_cadastrado)
        self.assertEqual(Evento.objects.count(), 0)  # envio automático ligado, mas importar não envia

    def test_atualiza_pelo_cpf_sem_apagar_o_que_esta_vazio(self):
        resp = self.enviar(csv_arquivo(["CPF", "Salário mensal", "E-mail"], ["52998224725", "3.500,00", ""]))
        self.assertContains(resp, "Atualizar")
        self.assertContains(resp, "Salário mensal")
        self.confirmar()
        self.maria.refresh_from_db()
        self.assertEqual(self.maria.salario, Decimal("3500.00"))
        self.assertEqual(self.maria.email, "maria@example.com")
        self.assertEqual(Funcionario.objects.count(), 1)

    def test_previa_mostra_erros_por_linha_e_nao_grava(self):
        cpf_errado = NOVA[:2] + ["111.111.111-12"] + NOVA[3:]
        data_errada = ["0003", "Bia Teste", "111.444.777-35", "31/02/1990"] + NOVA[4:]
        sem_cargo = NOVA[:10] + ["Astronauta", "2000"]
        resp = self.enviar(csv_arquivo(CABECALHO, cpf_errado, data_errada, sem_cargo))
        self.assertContains(resp, "CPF inválido")
        self.assertContains(resp, "Data de nascimento")
        self.assertContains(resp, "Astronauta")
        self.assertContains(resp, "Matrícula repetida na planilha")
        self.assertNotContains(resp, "Confirmar e gravar")
        linhas = resp.context["linhas"]
        self.assertEqual([l.numero for l in linhas if l.erros], [2, 3, 4])

        self.confirmar()  # mesmo forçando, nada é gravado enquanto houver erro
        self.assertEqual(Funcionario.objects.count(), 1)

    def test_importa_a_planilha_exportada_em_xlsx(self):
        wb = load_workbook(io.BytesIO(self.client.get(reverse("pessoal:exportar")).content))
        ws = wb.active
        ws.cell(row=2, column=list(ws[1]).index(next(c for c in ws[1] if c.value == "Salário mensal")) + 1, value=4100)
        saida = io.BytesIO()
        wb.save(saida)
        resp = self.enviar(SimpleUploadedFile("funcionarios.xlsx", saida.getvalue()))
        self.assertEqual([(l.acao, l.erros) for l in resp.context["linhas"]], [("atualizar", [])])
        self.assertEqual(resp.context["linhas"][0].mudancas, ["Salário mensal"])
        self.confirmar()
        self.maria.refresh_from_db()
        self.assertEqual(self.maria.salario, Decimal("4100.00"))

    def test_nunca_mistura_empresas(self):
        outra = fabrica.empresa(razao_social="Outra LTDA", nr_insc="11.444.777/0001-61")
        # Mesmo CPF em outra empresa não é atualizado: na empresa ativa é um cadastro novo.
        fabrica.funcionario(outra, cpf="123.456.789-09", salario=Decimal("1000"))
        resp = self.enviar(csv_arquivo(CABECALHO, NOVA))
        self.assertEqual(resp.context["linhas"][0].acao, "criar")

        # Trocou a empresa ativa entre a prévia e a confirmação: não grava.
        self.ativar(outra)
        resp = self.confirmar()
        self.assertRedirects(resp, self.url)
        self.assertFalse(Funcionario.objects.filter(empresa=self.emp, cpf="12345678909").exists())
        self.assertEqual(Funcionario.objects.get(empresa=outra, cpf="12345678909").salario, Decimal("1000"))

    def test_so_equipe_do_escritorio(self):
        # Quem não é do escritório nem chega às telas (PortalMiddleware): abrir vai para o portal, enviar dá 403.
        self.client.force_login(get_user_model().objects.create_user("cliente", password="x"))
        for url in (reverse("pessoal:exportar"), self.url, reverse("pessoal:lista")):
            self.assertRedirects(self.client.get(url), "/cliente/", fetch_redirect_response=False)
        self.assertEqual(self.enviar(csv_arquivo(CABECALHO, NOVA)).status_code, 403)


class EdicaoVaiAoESocialTest(TestCase):
    """Salvar a edição manda ao eSocial o que mudou: S-2205 (dados pessoais) ou S-2206 (contrato)."""

    def setUp(self):
        self.emp = fabrica.empresa()
        self.func = fabrica.funcionario(self.emp)
        Evento.objects.filter(pk=gerar_admissao(self.func).pk).update(status="aceito")
        self.client.force_login(get_user_model().objects.create_user("escritorio", password="x", is_staff=True))
        sessao = self.client.session
        sessao["empresa_id"] = self.emp.pk
        sessao.save()
        self.url = f"/funcionarios/{self.func.pk}/editar/"

    def dados(self, **mudar):
        form = self.client.get(self.url).context["form"]
        return {**{n: v for n in form.fields if (v := form[n].value()) is not None}, **mudar}

    def test_salario_vai_como_s2206_na_data_da_mudanca(self):
        r = self.client.post(self.url, self.dados(salario="3300.00", alteracao_em="2026-11-01"))
        self.assertEqual(r.status_code, 302)
        ev = Evento.objects.get(tipo="S-2206")
        self.assertEqual(ev.chave, f"S-2206:func:{self.func.pk}:2026-11-01")
        self.assertIn("<vrSalFx>3300.00</vrSalFx>", ev.xml)

    def test_endereco_vai_como_s2205(self):
        self.client.post(self.url, self.dados(logradouro="Rua Nova"))
        self.assertEqual(list(Evento.objects.filter(tipo__in=["S-2205", "S-2206"]).values_list("tipo", flat=True)),
                         ["S-2205"])

    def test_pix_nao_vai_ao_esocial(self):
        self.client.post(self.url, self.dados(chave_pix="pix-inventado"))
        self.assertFalse(Evento.objects.filter(tipo__in=["S-2205", "S-2206"]).exists())

    def test_sem_envio_automatico_nada_vai(self):
        self.emp.envio_automatico = False
        self.emp.save()
        self.client.post(self.url, self.dados(salario="3300.00"))
        self.assertFalse(Evento.objects.filter(tipo="S-2206").exists())

    def test_data_da_mudanca_antes_da_admissao(self):
        r = self.client.post(self.url, self.dados(salario="3300.00", alteracao_em="2025-02-28"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("alteracao_em", r.context["form"].errors)
