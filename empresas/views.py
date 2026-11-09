from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from folha.models import criar_rubricas_padrao

from .forms import CertificadoForm, EmpresaForm
from .models import Empresa


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
