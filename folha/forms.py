from datetime import date, timedelta

from django import forms

from pessoal.models import Funcionario

from . import calculo as c
from .conformidade import CRITICO, problemas_ferias
from .models import Competencia, Ferias, Lancamento, Rubrica

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
        fields = ["ano", "mes", "feriados", "data_pagamento", "data_adiantamento_13"]
        widgets = {"data_pagamento": DATA, "data_adiantamento_13": DATA}

    def clean_mes(self):
        mes = self.cleaned_data["mes"]
        if not 1 <= mes <= 12:
            raise forms.ValidationError("Mês deve estar entre 1 e 12.")
        return mes

    def clean(self):
        dados = super().clean()
        ano, mes = dados.get("ano"), dados.get("mes")
        if not ano or not mes:
            return dados
        qs = Competencia.objects.filter(empresa=self.empresa, tipo="mensal", ano=ano, mes=mes)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Esta competência já existe.")
        prox = date(ano + (mes == 12), mes % 12 + 1, 1)
        limite = c.quinto_dia_util(prox.year, prox.month)
        pg = dados.get("data_pagamento")
        if pg and pg > limite:
            self.add_error("data_pagamento", f"O salário deve ser pago até o 5º dia útil: {limite:%d/%m/%Y} "
                                             "(CLT art. 459, §1º).")
        ad = dados.get("data_adiantamento_13")
        if ad:
            if (ad.year, ad.month) != (ano, mes):
                self.add_error("data_adiantamento_13", "A 1ª parcela deve ser paga dentro do mês desta competência.")
            elif ad > date(ano, 11, 30):
                self.add_error("data_adiantamento_13", "A 1ª parcela do 13º vence em 30/11 (Lei 4.749/1965, art. 2º).")
        return dados


class LancamentoForm(forms.ModelForm):
    def __init__(self, *args, competencia=None, **kwargs):
        from .servico import PAPEIS_AUTOMATICOS

        super().__init__(*args, **kwargs)
        empresa = competencia.empresa
        self.fields["funcionario"].queryset = Funcionario.objects.filter(empresa=empresa).order_by("nome")
        self.fields["rubrica"].queryset = Rubrica.objects.filter(empresa=empresa, ativa=True).exclude(
            papel__in=PAPEIS_AUTOMATICOS
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
        label="Transmitir a DCTFWeb automaticamente depois do fechamento", required=False, initial=True,
        help_text="Recomendado. Sem isso, é preciso entrar no e-CAC e transmitir a DCTFWeb manualmente.",
    )


class FeriasForm(forms.ModelForm):
    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["funcionario"].queryset = Funcionario.objects.filter(
            empresa=empresa, data_desligamento__isnull=True
        ).order_by("nome")
        for campo in ("data_pagamento", "data_aviso"):
            self.fields[campo].required = False
            self.fields[campo].help_text += " Deixe em branco para o sistema sugerir."

    class Meta:
        model = Ferias
        fields = ["funcionario", "aquisitivo_inicio", "aquisitivo_fim", "faltas_injustificadas", "inicio", "dias",
                  "dias_abono", "data_pagamento", "data_aviso"]
        widgets = {f: DATA for f in ("aquisitivo_inicio", "aquisitivo_fim", "inicio", "data_pagamento", "data_aviso")}

    def clean(self):
        dados = super().clean()
        inicio = dados.get("inicio")
        if not inicio or not dados.get("funcionario") or not dados.get("dias"):
            return dados
        if not dados.get("data_pagamento"):
            dados["data_pagamento"] = c.dia_util_anterior(inicio - timedelta(days=2))
        if not dados.get("data_aviso"):
            dados["data_aviso"] = inicio - timedelta(days=30)
        tmp = Ferias(**{k: v for k, v in dados.items() if k in {f.name for f in Ferias._meta.fields}})
        tmp.pk = self.instance.pk
        criticos = [p for p in problemas_ferias(tmp) if p[0] == CRITICO]
        for _, titulo, detalhe, base in criticos:
            self.add_error(None, f"{titulo.capitalize()}: {detalhe} ({base})")
        return dados

    def save(self, commit=True):
        self.instance.data_pagamento = self.cleaned_data["data_pagamento"]
        self.instance.data_aviso = self.cleaned_data["data_aviso"]
        return super().save(commit)


class RescisaoForm(forms.ModelForm):
    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["funcionario"].queryset = Funcionario.objects.filter(
            empresa=empresa, data_desligamento__isnull=True
        ).order_by("nome")
        self.fields["data_pagamento"].required = False
        self.fields["data_pagamento"].help_text += " Deixe em branco para usar o último dia do prazo."

    class Meta:
        from .models import Rescisao

        model = Rescisao
        fields = ["funcionario", "motivo", "tipo_aviso", "data_aviso", "data_desligamento", "data_pagamento",
                  "saldo_fgts", "faltas_periodo_ferias"]
        widgets = {f: DATA for f in ("data_aviso", "data_desligamento", "data_pagamento")}

    def clean(self):
        dados = super().clean()
        f, deslig = dados.get("funcionario"), dados.get("data_desligamento")
        if not f or not deslig:
            return dados
        if deslig < f.data_admissao:
            self.add_error("data_desligamento", "O desligamento não pode ser antes da admissão.")
        prazo = deslig + timedelta(days=10)
        if not dados.get("data_pagamento"):
            dados["data_pagamento"] = prazo
        elif dados["data_pagamento"] > prazo:
            self.add_error("data_pagamento", f"O prazo legal é {prazo:%d/%m/%Y} (CLT art. 477, §6º). "
                                             "Pagar depois gera multa de um salário (art. 477, §8º).")
        if dados.get("motivo") in {"07", "08"} and dados.get("tipo_aviso") == "indenizado":
            self.add_error("tipo_aviso", "No pedido de demissão o aviso é do empregado: escolha trabalhado, "
                                         "dispensado pela empresa ou não cumprido.")
        if dados.get("motivo") in {"01", "06", "10", "03", "04"} and dados.get("tipo_aviso") not in {"nenhum", None}:
            dados["tipo_aviso"] = "nenhum"
        return dados

    def save(self, commit=True):
        self.instance.data_pagamento = self.cleaned_data["data_pagamento"]
        self.instance.tipo_aviso = self.cleaned_data["tipo_aviso"]
        return super().save(commit)
