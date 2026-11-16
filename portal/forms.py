from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q

from empresas.consulta_cnpj import consultar_cnpj
from empresas.models import Empresa
from empresas.validators import normalizar_cnpj, so_digitos, validar_cnpj, validar_cpf

TERMOS_VERSAO = "2026-11-16"


def _campo_senha(rotulo):
    return forms.CharField(label=rotulo, strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))


class DonaForm(forms.Form):
    """Conta nova da dona: dados pessoais, senha dentro das regras do Django e aceite dos termos."""

    nome = forms.CharField(label="Seu nome completo", max_length=150, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    cpf = forms.CharField(label="Seu CPF", max_length=14, widget=forms.TextInput(attrs={"inputmode": "numeric"}))
    email = forms.EmailField(label="Seu e-mail", max_length=150, help_text="Você vai entrar no site com ele.",
                             widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    senha1 = _campo_senha("Crie uma senha")
    senha2 = _campo_senha("Repita a senha")
    aceite = forms.BooleanField(label="Li e aceito os Termos de uso e a Política de privacidade")

    def clean_cpf(self):
        validar_cpf(self.cleaned_data["cpf"])
        return so_digitos(self.cleaned_data["cpf"])

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(Q(username__iexact=email) | Q(email__iexact=email)).exists():
            raise ValidationError("Já existe uma conta com esse e-mail. Entre com ele na tela de entrar.")
        return email

    def clean(self):
        d = super().clean()
        s1, s2 = d.get("senha1"), d.get("senha2")
        if s1 and s2 and s1 != s2:
            self.add_error("senha2", "As duas senhas não são iguais.")
        elif s1:
            try:
                validate_password(s1, User(username=d.get("email", ""), email=d.get("email", ""), first_name=d.get("nome", "")))
            except ValidationError as e:
                self.add_error("senha1", e)
        return d


class ConviteForm(DonaForm):
    pass


class CadastroForm(DonaForm):
    celular = forms.CharField(label="Seu celular com DDD", max_length=20,
                              widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel"}))
    cnpj = forms.CharField(label="CNPJ da empresa", max_length=18)
    razao_social = forms.CharField(label="Nome da empresa (razão social)", max_length=115, required=False,
                                   help_text="Só se pedirmos: buscamos o nome pelo CNPJ.")
    funcionarios = forms.IntegerField(label="Quantas pessoas trabalham registradas hoje?", min_value=0, max_value=9999,
                                      help_text="Se ainda não tem ninguém, coloque 0.")
    site = forms.CharField(required=False)  # armadilha para robôs: fica escondida, gente de verdade não preenche

    dados_cnpj: dict = {}

    def clean_cnpj(self):
        validar_cnpj(self.cleaned_data["cnpj"])
        cnpj = normalizar_cnpj(self.cleaned_data["cnpj"])
        if Empresa.objects.filter(nr_insc=cnpj).exists():
            raise ValidationError("Essa empresa já tem cadastro. Fale com o escritório.")
        return cnpj

    def clean(self):
        d = super().clean()
        if not self.errors:  # só consulta a Receita com o resto certo
            self.dados_cnpj = consultar_cnpj(d["cnpj"]) or {}
            if not (self.dados_cnpj.get("razao_social") or d.get("razao_social", "").strip()):
                self.add_error("razao_social", "Não achamos a empresa na Receita agora. Digite a razão social.")
        return d
