from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from empresas.mixins import EmpresaRequiredMixin

from .forms import CargoForm, DependenteForm, DesligamentoForm, FuncionarioForm
from .models import Cargo, Dependente, Funcionario


class CargoListView(EmpresaRequiredMixin, CreateView):
    """Lista os cargos e permite cadastrar um novo na mesma tela."""

    model = Cargo
    form_class = CargoForm
    template_name = "pessoal/cargos.html"
    success_url = reverse_lazy("pessoal:cargos")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["cargos"] = Cargo.objects.filter(empresa=self.empresa)
        return ctx

    def form_valid(self, form):
        form.instance.empresa = self.empresa
        messages.success(self.request, "Cargo cadastrado.")
        return super().form_valid(form)


class CargoUpdateView(EmpresaRequiredMixin, UpdateView):
    model = Cargo
    form_class = CargoForm
    template_name = "form.html"
    extra_context = {"titulo": "Editar cargo"}
    success_url = reverse_lazy("pessoal:cargos")


class FuncionarioListView(EmpresaRequiredMixin, ListView):
    model = Funcionario
    template_name = "pessoal/lista.html"

    def get_queryset(self):
        qs = super().get_queryset().select_related("cargo")
        situacao = self.request.GET.get("situacao", "ativos")
        if situacao == "ativos":
            qs = qs.filter(data_desligamento__isnull=True)
        elif situacao == "desligados":
            qs = qs.filter(data_desligamento__isnull=False)
        if busca := self.request.GET.get("q"):
            qs = qs.filter(nome__icontains=busca) | qs.filter(cpf__contains=busca) | qs.filter(matricula=busca)
        return qs


class FuncionarioFormMixin:
    model = Funcionario
    form_class = FuncionarioForm
    template_name = "form.html"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["empresa"] = self.empresa
        return kw

    def get_success_url(self):
        return reverse("pessoal:detalhe", args=[self.object.pk])


class FuncionarioCreateView(EmpresaRequiredMixin, FuncionarioFormMixin, CreateView):
    extra_context = {"titulo": "Novo funcionário"}

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.empresa and not request.empresa.cargos.exists():
            messages.info(request, "Cadastre ao menos um cargo antes do funcionário.")
            return redirect("pessoal:cargos")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.empresa = self.empresa
        messages.success(self.request, "Funcionário cadastrado. Gere o evento S-2200 (admissão) na ficha dele.")
        return super().form_valid(form)


class FuncionarioUpdateView(EmpresaRequiredMixin, FuncionarioFormMixin, UpdateView):
    extra_context = {"titulo": "Editar funcionário"}


class FuncionarioDetailView(EmpresaRequiredMixin, DetailView):
    model = Funcionario
    template_name = "pessoal/detalhe.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_dependente"] = DependenteForm()
        ctx["eventos"] = self.object.evento_set.all()[:20]
        ctx["holerites"] = self.object.holerites.select_related("competencia")[:12]
        return ctx


class DesligamentoView(EmpresaRequiredMixin, UpdateView):
    model = Funcionario
    form_class = DesligamentoForm
    template_name = "form.html"
    extra_context = {
        "titulo": "Desligar funcionário",
        "aviso": "Depois de salvar, gere o S-2299 na ficha do funcionário. O cálculo das verbas rescisórias "
                 "(TRCT) ainda não é feito automaticamente por esta versão.",
    }

    def get_success_url(self):
        return reverse("pessoal:detalhe", args=[self.object.pk])


class DependenteCreateView(EmpresaRequiredMixin, CreateView):
    model = Dependente
    form_class = DependenteForm
    template_name = "form.html"
    extra_context = {"titulo": "Novo dependente"}

    def get_queryset(self):
        return Dependente.objects.filter(funcionario__empresa=self.empresa)

    def form_valid(self, form):
        form.instance.funcionario = get_object_or_404(Funcionario, pk=self.kwargs["pk"], empresa=self.empresa)
        messages.success(self.request, "Dependente incluído.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("pessoal:detalhe", args=[self.kwargs["pk"]])


@login_required
@require_POST
def excluir_dependente(request, pk):
    dep = get_object_or_404(Dependente, pk=pk, funcionario__empresa=request.empresa)
    func_pk = dep.funcionario_id
    dep.delete()
    messages.success(request, "Dependente excluído.")
    return redirect("pessoal:detalhe", pk=func_pk)
