from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from empresas.mixins import EmpresaRequiredMixin
from esocial.servico import ErroESocial, data_pagamento_padrao, fechar_competencia

from .forms import CompetenciaForm, FechamentoForm, LancamentoForm, RubricaForm
from .models import Competencia, Holerite, Lancamento, Rubrica, criar_rubricas_padrao
from .servico import ErroCalculo, calcular_competencia, resumo_encargos
from .tabelas import tabela_atualizada, tabelas_do_ano


class RubricaListView(EmpresaRequiredMixin, ListView):
    model = Rubrica
    template_name = "folha/rubricas.html"

    def get_queryset(self):
        criar_rubricas_padrao(self.empresa)
        return super().get_queryset()


class RubricaCreateView(EmpresaRequiredMixin, CreateView):
    model = Rubrica
    form_class = RubricaForm
    template_name = "form.html"
    extra_context = {
        "titulo": "Nova rubrica",
        "aviso": "Depois de criar a rubrica, gere o evento S-1010 dela em eSocial > Eventos iniciais.",
    }
    success_url = reverse_lazy("folha:rubricas")

    def form_valid(self, form):
        form.instance.empresa = self.empresa
        return super().form_valid(form)


class RubricaUpdateView(EmpresaRequiredMixin, UpdateView):
    model = Rubrica
    form_class = RubricaForm
    template_name = "form.html"
    extra_context = {"titulo": "Editar rubrica"}
    success_url = reverse_lazy("folha:rubricas")


class CompetenciaListView(EmpresaRequiredMixin, ListView):
    model = Competencia
    template_name = "folha/competencias.html"


class CompetenciaCreateView(EmpresaRequiredMixin, CreateView):
    model = Competencia
    form_class = CompetenciaForm
    template_name = "form.html"
    extra_context = {"titulo": "Nova competência"}

    def get_initial(self):
        from django.utils import timezone

        hoje = timezone.localdate()
        return {
            "ano": hoje.year,
            "mes": hoje.month,
            "data_pagamento": data_pagamento_padrao(hoje.year, hoje.month, self.empresa.dia_pagamento),
        }

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["empresa"] = self.empresa
        return kw

    def form_valid(self, form):
        form.instance.empresa = self.empresa
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("folha:competencia", args=[self.object.pk])


class CompetenciaDetailView(EmpresaRequiredMixin, DetailView):
    model = Competencia
    template_name = "folha/competencia.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        comp = self.object
        ctx["form_lancamento"] = LancamentoForm(competencia=comp)
        ctx["lancamentos"] = comp.lancamentos.select_related("funcionario", "rubrica")
        ctx["holerites"] = comp.holerites.select_related("funcionario")
        ctx["resumo"] = resumo_encargos(comp) if comp.status != "aberta" else None
        ctx["form_fechamento"] = FechamentoForm()
        ctx["tabela"] = tabelas_do_ano(comp.ano)
        ctx["tabela_atualizada"] = tabela_atualizada(comp.ano)
        ctx["eventos"] = comp.evento_set.all()
        return ctx


def _competencia(request, pk) -> Competencia:
    return get_object_or_404(Competencia, pk=pk, empresa=request.empresa)


@login_required
@require_POST
def novo_lancamento(request, pk):
    comp = _competencia(request, pk)
    if not comp.editavel:
        messages.error(request, "Competência fechada.")
        return redirect("folha:competencia", pk=pk)
    form = LancamentoForm(request.POST, competencia=comp)
    if form.is_valid():
        form.instance.competencia = comp
        form.save()
        if comp.status == "calculada":
            comp.status = "aberta"
            comp.save(update_fields=["status"])
        messages.success(request, "Lançamento incluído. Recalcule a folha.")
    else:
        for erro in form.errors.values():
            messages.error(request, " ".join(erro))
    return redirect("folha:competencia", pk=pk)


@login_required
@require_POST
def excluir_lancamento(request, pk):
    lanc = get_object_or_404(Lancamento, pk=pk, competencia__empresa=request.empresa)
    comp = lanc.competencia
    if comp.editavel:
        lanc.delete()
        if comp.status == "calculada":
            comp.status = "aberta"
            comp.save(update_fields=["status"])
        messages.success(request, "Lançamento excluído. Recalcule a folha.")
    return redirect("folha:competencia", pk=comp.pk)


@login_required
@require_POST
def calcular(request, pk):
    comp = _competencia(request, pk)
    try:
        avisos = calcular_competencia(comp)
    except ErroCalculo as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Folha calculada: {comp.holerites.count()} holerite(s).")
        for aviso in avisos:
            messages.warning(request, aviso)
    return redirect("folha:competencia", pk=pk)


@login_required
@require_POST
def fechar(request, pk):
    comp = _competencia(request, pk)
    form = FechamentoForm(request.POST)
    form.is_valid()
    try:
        eventos = fechar_competencia(comp, transmitir_dctfweb=form.cleaned_data.get("transmitir_dctfweb", False))
    except ErroESocial as exc:
        messages.error(request, str(exc))
        return redirect("folha:competencia", pk=pk)
    com_erro = [e for e in eventos if e.status == "erro"]
    messages.success(request, f"Competência fechada. {len(eventos)} evento(s) do eSocial gerado(s).")
    if com_erro:
        messages.error(request, f"{len(com_erro)} evento(s) com erro de validação. Confira em eSocial > Eventos.")
    return redirect("esocial:eventos")


@login_required
def holerite(request, pk):
    hol = get_object_or_404(
        Holerite.objects.select_related("funcionario__cargo", "competencia__empresa"),
        pk=pk, competencia__empresa=request.empresa,
    )
    itens = hol.itens.select_related("rubrica")
    return render(request, "folha/holerite.html", {
        "h": hol,
        "proventos": [i for i in itens if i.rubrica.tipo == 1],
        "descontos": [i for i in itens if i.rubrica.tipo == 2],
    })


@login_required
def holerites_impressao(request, pk):
    comp = _competencia(request, pk)
    lista = []
    for hol in comp.holerites.select_related("funcionario__cargo", "competencia__empresa"):
        itens = hol.itens.select_related("rubrica")
        lista.append({
            "h": hol,
            "proventos": [i for i in itens if i.rubrica.tipo == 1],
            "descontos": [i for i in itens if i.rubrica.tipo == 2],
        })
    return render(request, "folha/holerites_lote.html", {"lista": lista, "comp": comp})
