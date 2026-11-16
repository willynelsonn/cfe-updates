"""O que a dona responde em cada pedido, em linguagem simples. Nada aqui grava em funcionário, férias ou rescisão."""

from datetime import date
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from empresas.validators import formatar_cpf, so_digitos, validar_cpf
from folha.custo import custo_mensal
from folha.templatetags.ui import moeda
from pessoal.models import Funcionario

from .anexos import tipo_do_arquivo

DATA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
TEXTO = forms.Textarea(attrs={"rows": 3})


def _data(rotulo, **kw):
    return forms.DateField(label=rotulo, widget=DATA, **kw)


def dinheiro(rotulo, **kw):
    return forms.DecimalField(label=rotulo, max_digits=12, decimal_places=2, min_value=0, localize=True,
                              widget=forms.TextInput(attrs={"inputmode": "decimal"}), **kw)


def _arquivo(rotulo, required=False):
    return forms.FileField(label=rotulo, required=required,
                           widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,application/pdf"}),
                           help_text="Foto (JPG ou PNG) ou PDF, até 5 MB.")


def _pessoa(**kw):
    return forms.ModelChoiceField(label="Quem é a pessoa", queryset=Funcionario.objects.none(),
                                  empty_label="Escolha", **kw)


def _validar_arquivo(arquivo):
    if arquivo:
        tipo_do_arquivo(arquivo)
    return arquivo


class PedidoForm(forms.Form):
    """Base: pessoas só da empresa da dona, arquivo conferido e respostas prontas para JSON."""

    arquivo = _arquivo("Foto ou PDF (se quiser)")

    def __init__(self, *args, empresa, **kwargs):
        super().__init__(*args, **kwargs)
        self.empresa = empresa
        if "funcionario" in self.fields:
            self.fields["funcionario"].queryset = Funcionario.objects.filter(
                empresa=empresa, data_desligamento__isnull=True).order_by("nome")
        self.order_fields([f for f in self.fields if f != "arquivo"] + ["arquivo"])

    def clean_arquivo(self):
        return _validar_arquivo(self.cleaned_data.get("arquivo"))

    def respostas(self) -> dict:
        r = {}
        for nome, v in self.cleaned_data.items():
            if nome in ("arquivo", "funcionario") or v in (None, ""):
                continue
            r[nome] = v.isoformat() if isinstance(v, date) else str(v) if isinstance(v, Decimal) else v
        return r


class ContrateiForm(PedidoForm):
    nome = forms.CharField(label="Nome completo da pessoa", max_length=70)
    cpf = forms.CharField(label="CPF da pessoa", max_length=14, widget=forms.TextInput(attrs={"inputmode": "numeric"}))
    data_nascimento = _data("Data de nascimento")
    telefone = forms.CharField(label="Celular da pessoa", max_length=20, required=False)
    email = forms.EmailField(label="E-mail da pessoa", required=False)
    cep = forms.CharField(label="CEP de onde a pessoa mora", max_length=9)
    salario = dinheiro("Salário por mês (R$)")
    horario = forms.CharField(label="Dias e horário de trabalho", max_length=100,
                              help_text="Ex.: segunda a sexta, das 8h às 17h, com 1 hora de almoço.")
    vale_transporte = forms.BooleanField(label="Vai usar vale-transporte", required=False)
    funcao = forms.CharField(label="O que a pessoa vai fazer", max_length=100,
                             help_text="Ex.: atender no balcão e fazer pães.")
    data_inicio = _data("Primeiro dia de trabalho")
    arquivo = _arquivo("Fotos dos documentos (RG ou CNH, CPF e carteira de trabalho)")

    def clean_cpf(self):
        validar_cpf(self.cleaned_data["cpf"])
        return so_digitos(self.cleaned_data["cpf"])


class SairForm(PedidoForm):
    funcionario = _pessoa()
    ultimo_dia = _data("Último dia de trabalho")
    quem_pediu = forms.ChoiceField(label="Quem pediu para sair", widget=forms.RadioSelect, choices=[
        ("pessoa", "A própria pessoa pediu"),
        ("empresa", "A empresa vai dispensar"),
        ("acordo", "Acordo entre os dois"),
        ("fim_contrato", "Acabou o contrato de experiência ou com prazo"),
        ("justa_causa", "Justa causa (fale com o escritório antes)"),
    ])
    aviso = forms.ChoiceField(label="Aviso prévio", widget=forms.RadioSelect,
                              help_text="Aviso prévio são os dias entre avisar e sair (30 dias ou mais).", choices=[
                                  ("trabalha", "Vai trabalhar os dias do aviso"),
                                  ("nao_trabalha", "Não vai trabalhar o aviso"),
                                  ("nao_sei", "Não sei"),
                              ])
    observacao = forms.CharField(label="Quer contar mais alguma coisa?", required=False, widget=TEXTO, max_length=2000)


class FeriasPedidoForm(PedidoForm):
    funcionario = _pessoa()
    inicio = _data("Primeiro dia de férias", help_text="Avise a pessoa 30 dias antes. O pagamento sai até 2 dias antes.")
    dias = forms.IntegerField(label="Quantos dias de descanso", min_value=5, max_value=30, initial=30)
    vender_10 = forms.BooleanField(label="A pessoa quer vender 10 dias (receber em dinheiro)", required=False)

    def clean_inicio(self):
        inicio = self.cleaned_data["inicio"]
        if inicio < timezone.localdate():
            raise ValidationError("As férias precisam começar hoje ou depois.")
        return inicio

    def clean(self):
        d = super().clean()
        if d.get("vender_10") and (d.get("dias") or 0) > 20:
            raise ValidationError("Vendendo 10 dias, sobram no máximo 20 dias de descanso.")
        return d


class AlterarForm(PedidoForm):
    MUDANCAS = ("cep", "endereco", "telefone", "salario", "cargo", "banco_pix")

    funcionario = _pessoa()
    cep = forms.CharField(label="Novo CEP", max_length=9, required=False)
    endereco = forms.CharField(label="Novo endereço (rua, número e bairro)", max_length=150, required=False)
    telefone = forms.CharField(label="Novo celular", max_length=20, required=False)
    salario = dinheiro("Novo salário por mês (R$)", required=False)
    cargo = forms.CharField(label="Nova função (o que a pessoa passa a fazer)", max_length=100, required=False)
    banco_pix = forms.CharField(label="Novo banco ou chave Pix para o salário", max_length=100, required=False)
    a_partir_de = _data("A partir de quando", required=False)
    observacao = forms.CharField(label="Quer contar mais alguma coisa?", required=False, widget=TEXTO, max_length=2000)

    def clean(self):
        d = super().clean()
        if not any(d.get(c) not in (None, "") for c in self.MUDANCAS):
            raise ValidationError("Preencha pelo menos uma mudança.")
        return d


class DocumentoForm(PedidoForm):
    assunto = forms.ChoiceField(label="Do que se trata", choices=[
        ("atestado", "Atestado médico"),
        ("exame", "Exame (admissão, demissão ou periódico)"),
        ("documento_pessoal", "Documento de alguém da equipe"),
        ("outro", "Outro"),
    ])
    funcionario = _pessoa(required=False)
    descricao = forms.CharField(label="Explique em poucas palavras", max_length=300, required=False)
    arquivo = _arquivo("Foto ou PDF do documento", required=True)


class DuvidaForm(PedidoForm):
    texto = forms.CharField(label="Sua dúvida ou recado", widget=forms.Textarea(attrs={"rows": 5}), max_length=2000)


FORMULARIOS = {"contratei": ContrateiForm, "sair": SairForm, "ferias": FeriasPedidoForm, "alterar": AlterarForm,
               "documento": DocumentoForm, "duvida": DuvidaForm}


class MensagemForm(forms.Form):
    texto = forms.CharField(label="Mensagem", required=False, widget=TEXTO, max_length=2000)
    arquivo = _arquivo("Foto ou PDF (se quiser)")

    def clean_arquivo(self):
        return _validar_arquivo(self.cleaned_data.get("arquivo"))

    def clean(self):
        d = super().clean()
        if not d.get("texto", "").strip() and not d.get("arquivo") and not self.errors:
            raise ValidationError("Escreva uma mensagem ou escolha um arquivo.")
        return d


def resumo(pedido) -> list[tuple[str, str]]:
    """Rótulo e valor legível de cada resposta (sem campos vazios; a pessoa aparece à parte)."""
    form = FORMULARIOS[pedido.tipo](empresa=pedido.empresa)
    linhas = []
    for nome, campo in form.fields.items():
        v = pedido.respostas.get(nome)
        if nome in ("arquivo", "funcionario") or v in (None, ""):
            continue
        if isinstance(campo, forms.BooleanField):
            v = "Sim" if v else "Não"
        elif isinstance(campo, forms.ChoiceField):
            v = dict(campo.choices).get(v, v)
        elif isinstance(campo, forms.DateField):
            v = date.fromisoformat(v).strftime("%d/%m/%Y")
        elif isinstance(campo, forms.DecimalField):
            v = moeda(v)
        elif nome == "cpf":
            v = formatar_cpf(v)
        linhas.append((campo.label, str(v)))
    if pedido.tipo == "contratei" and pedido.respostas.get("salario"):
        total = custo_mensal(pedido.empresa, Decimal(pedido.respostas["salario"])).total
        linhas.append(("Custo estimado por mês para a empresa", f"{moeda(total)} (estimativa)"))
    return linhas
