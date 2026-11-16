from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from folha.models import criar_rubricas_padrao

from .acesso import eh_escritorio
from .forms import CertificadoForm, EmpresaForm, ValidarEmpresaForm
from .models import Convite, Empresa


class EmpresaListView(LoginRequiredMixin, ListView):
    model = Empresa
    template_name = "empresas/lista.html"


class EmpresaCreateView(LoginRequiredMixin, CreateView):
    model = Empresa
    form_class = EmpresaForm
    template_name = "form.html"
    extra_context = {"titulo": "Nova empresa"}
    success_url = reverse_lazy("empresas:lista")

    def form_valid(self, form):
        resp = super().form_valid(form)
        criar_rubricas_padrao(self.object)
        self.request.session["empresa_id"] = self.object.pk
        messages.success(self.request, "Empresa cadastrada. Agora envie o certificado digital e os eventos iniciais.")
        return resp


class EmpresaUpdateView(LoginRequiredMixin, UpdateView):
    model = Empresa
    form_class = EmpresaForm
    template_name = "form.html"
    extra_context = {"titulo": "Editar empresa"}
    success_url = reverse_lazy("empresas:lista")


@login_required
@require_POST
def selecionar(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk, ativa=True)
    request.session["empresa_id"] = empresa.pk
    return redirect(request.POST.get("next") or "dashboard")


@login_required
def certificado(request, pk):
    empresa = get_object_or_404(Empresa, pk=pk)
    form = CertificadoForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        cert = form.cleaned_data["certificado"]
        if empresa.certificado:
            empresa.certificado.delete(save=False)
        empresa.certificado.save(form.cleaned_data["arquivo"].name, ContentFile(form.cleaned_data["arquivo"].read()),
                                 save=False)
        empresa.definir_senha_certificado(form.cleaned_data["senha"])
        empresa.save()
        messages.success(request, f"Certificado de {cert.titular} salvo (válido até {cert.validade:%d/%m/%Y}).")
        return redirect("empresas:lista")
    return render(request, "form.html", {"form": form, "titulo": f"Certificado digital - {empresa}", "multipart": True})


@login_required
@user_passes_test(eh_escritorio)
def validar(request, pk):
    """O escritório confere a empresa que a dona cadastrou: completa os dados técnicos e libera, ou recusa."""
    # Empresa já ativa não passa por aqui: liberar de novo desligaria o envio automático dela.
    empresa = get_object_or_404(Empresa, pk=pk, situacao__in=["em_analise", "recusada"])
    acao = request.POST.get("acao") if request.method == "POST" else None
    form = ValidarEmpresaForm(request.POST if acao == "liberar" else None, instance=empresa)
    erro_motivo = ""
    if acao == "recusar":
        motivo = request.POST.get("motivo", "").strip()
        if motivo:
            Empresa.objects.filter(pk=pk).update(situacao="recusada", ativa=False, motivo_recusa=motivo,
                                                 validada_em=timezone.now(), validada_por=request.user)
            messages.success(request, f"{empresa.razao_social} recusada. A dona vê o motivo ao entrar.")
            return redirect("empresas:lista")
        erro_motivo = "Escreva o motivo: a dona vai ler."
    elif acao == "liberar" and form.is_valid():
        with transaction.atomic():
            e = form.save(commit=False)
            e.situacao, e.ativa, e.envio_automatico, e.motivo_recusa = "ativa", True, False, ""
            e.transmissor_cnpj = e.transmissor_cnpj or settings.FOLHA_ESCRITORIO_CNPJ
            e.validada_em, e.validada_por = timezone.now(), request.user
            e.save()
            criar_rubricas_padrao(e)
        messages.success(request, f"{e.razao_social} liberada. Envie o certificado para ligar o envio ao eSocial.")
        return redirect("empresas:lista")
    return render(request, "empresas/validar.html", {
        "empresa": empresa, "form": form, "erro_motivo": erro_motivo,
        "acessos": empresa.acessos.select_related("usuario"),
    })


@login_required
@user_passes_test(eh_escritorio)
@require_POST
def convidar(request, pk):
    """Gera o link de uso único para a dona criar a conta. O link aparece só nesta resposta."""
    empresa = get_object_or_404(Empresa, pk=pk)
    _, codigo = Convite.criar(empresa, request.user)
    link = request.build_absolute_uri(reverse("portal:convite", args=[codigo]))
    texto = f"Olá! Este é o seu link para entrar no portal da {empresa.razao_social} (vale por 7 dias): {link}"
    return render(request, "empresas/convite_link.html", {
        "empresa": empresa, "link": link, "whatsapp": "https://wa.me/?text=" + quote(texto),
    })
