from django import forms

from pessoal.models import Funcionario

from .models import Competencia, Lancamento, Rubrica

DATA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class RubricaForm(forms.ModelForm):
    class Meta:
        model = Rubrica
        fields = ["codigo", "descricao", "tipo", "natureza", "inc_cp", "inc_irrf", "inc_fgts", "papel", "ativa"]


class CompetenciaForm(forms.ModelForm):
    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.empresa = empresa

    class Meta:
        model = Competencia
        fields = ["ano", "mes", "feriados", "data_pagamento"]
        widgets = {"data_pagamento": DATA}

    def clean_mes(self):
        mes = self.cleaned_data["mes"]
        if not 1 <= mes <= 12:
            raise forms.ValidationError("Mês deve estar entre 1 e 12.")
        return mes

    def clean(self):
        dados = super().clean()
        if Competencia.objects.filter(empresa=self.empresa, ano=dados.get("ano"), mes=dados.get("mes")).exists():
            raise forms.ValidationError("Esta competência já existe.")
        return dados


class LancamentoForm(forms.ModelForm):
    def __init__(self, *args, competencia=None, **kwargs):
        super().__init__(*args, **kwargs)
        empresa = competencia.empresa
        self.fields["funcionario"].queryset = Funcionario.objects.filter(empresa=empresa).order_by("nome")
        self.fields["rubrica"].queryset = Rubrica.objects.filter(empresa=empresa, ativa=True).exclude(
            papel__in=["salario", "dsr_he", "insalubridade", "periculosidade", "salario_familia", "inss", "irrf",
                       "vale_transporte"]
        )

    class Meta:
        model = Lancamento
        fields = ["funcionario", "rubrica", "quantidade", "valor", "observacao"]

    def clean(self):
        dados = super().clean()
        rub = dados.get("rubrica")
        if rub and rub.papel in {"he50", "he100", "ad_noturno", "faltas", "dsr_faltas"}:
            if not dados.get("quantidade"):
                raise forms.ValidationError("Informe a quantidade (horas ou dias) para esta rubrica.")
        elif rub and dados.get("valor") is None:
            raise forms.ValidationError("Informe o valor em R$ para esta rubrica.")
        return dados


class FechamentoForm(forms.Form):
    transmitir_dctfweb = forms.BooleanField(
        label="Transmitir a DCTFWeb automaticamente após o fechamento (transDCTFWeb)", required=False, initial=True
    )
