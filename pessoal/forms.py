from django import forms

from .models import Cargo, Dependente, Funcionario

DATA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class CargoForm(forms.ModelForm):
    class Meta:
        model = Cargo
        fields = ["nome", "cbo"]


class FuncionarioForm(forms.ModelForm):
    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.empresa = empresa
        if empresa is not None:
            self.fields["cargo"].queryset = Cargo.objects.filter(empresa=empresa)

    class Meta:
        model = Funcionario
        exclude = ["empresa", "data_desligamento", "motivo_desligamento", "aviso_previo_indenizado"]
        widgets = {"data_nascimento": DATA, "data_admissao": DATA, "data_termino": DATA}

    def clean_matricula(self):
        matricula = self.cleaned_data["matricula"].strip()
        qs = Funcionario.objects.filter(empresa=self.empresa, matricula=matricula)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Já existe um funcionário com esta matrícula.")
        return matricula


class DesligamentoForm(forms.ModelForm):
    class Meta:
        model = Funcionario
        fields = ["data_desligamento", "motivo_desligamento", "aviso_previo_indenizado"]
        widgets = {"data_desligamento": DATA}

    def clean(self):
        dados = super().clean()
        if not dados.get("data_desligamento") or not dados.get("motivo_desligamento"):
            raise forms.ValidationError("Informe a data e o motivo do desligamento.")
        if dados["data_desligamento"] < self.instance.data_admissao:
            raise forms.ValidationError("O desligamento não pode ser anterior à admissão.")
        return dados


class DependenteForm(forms.ModelForm):
    class Meta:
        model = Dependente
        exclude = ["funcionario"]
        widgets = {"data_nascimento": DATA}
