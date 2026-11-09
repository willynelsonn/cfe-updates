from django import forms

from esocial.assinatura import ErroCertificado, carregar_pfx

from .models import Empresa


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = [
            "razao_social", "nome_fantasia", "tp_insc", "nr_insc", "class_trib", "simples_anexo_iv", "cnae",
            "fpas", "cod_terceiros", "aliq_terceiros", "aliq_rat", "fap", "cnpj_sindicato", "inicio_esocial",
            "municipio", "uf", "dia_pagamento", "ambiente_esocial", "transmissor_cnpj", "envio_automatico",
            "esocial_ja_iniciado",
        ]


class CertificadoForm(forms.Form):
    arquivo = forms.FileField(label="Arquivo do certificado A1 (.pfx ou .p12)")
    senha = forms.CharField(label="Senha do certificado", widget=forms.PasswordInput)

    def clean(self):
        dados = super().clean()
        arquivo, senha = dados.get("arquivo"), dados.get("senha")
        if arquivo and senha is not None:
            conteudo = arquivo.read()
            arquivo.seek(0)
            try:
                cert = carregar_pfx(conteudo, senha)
            except ErroCertificado as exc:
                raise forms.ValidationError(str(exc)) from exc
            if cert.vencido:
                raise forms.ValidationError(f"Certificado vencido em {cert.validade:%d/%m/%Y}.")
            dados["certificado"] = cert
        return dados
