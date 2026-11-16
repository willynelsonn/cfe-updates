import base64

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.text import slugify
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from empresas.mixins import EmpresaRequiredMixin
from esocial.servico import ErroESocial, gerar_admissao, gerar_desligamento, tentar_processar
from portal.aprovacao import PedidoMixin

from . import planilha
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


class FuncionarioCreateView(EmpresaRequiredMixin, PedidoMixin, FuncionarioFormMixin, CreateView):
    extra_context = {"titulo": "Novo funcionário"}
    tipo_pedido = "contratei"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.empresa and not request.empresa.cargos.exists():
            messages.info(request, "Cadastre ao menos um cargo antes do funcionário.")
            return redirect("pessoal:cargos")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.empresa = self.empresa
        resp = super().form_valid(form)
        self.aprovar_pedido()
        func = self.object
        if self.empresa.envio_automatico and not func.esocial_ja_cadastrado:
            try:
                gerar_admissao(func)
            except ErroESocial as exc:
                messages.warning(self.request, f"Funcionário salvo, mas a admissão não foi para o eSocial: {exc}")
                return resp
            messages.success(self.request, "Funcionário cadastrado e admissão (S-2200) colocada na fila do eSocial.")
            if problema := tentar_processar(self.empresa):
                messages.warning(self.request, problema)
        else:
            messages.success(self.request, "Funcionário cadastrado.")
        return resp


class FuncionarioUpdateView(EmpresaRequiredMixin, PedidoMixin, FuncionarioFormMixin, UpdateView):
    extra_context = {"titulo": "Editar funcionário"}
    tipo_pedido = "alterar"

    def form_valid(self, form):
        resp = super().form_valid(form)
        self.aprovar_pedido()
        return resp


class FuncionarioDetailView(EmpresaRequiredMixin, DetailView):
    model = Funcionario
    template_name = "pessoal/detalhe.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_dependente"] = DependenteForm()
        ctx["eventos"] = self.object.evento_set.all()[:20]
        ctx["holerites"] = self.object.holerites.select_related("competencia")[:12]
        ctx["ferias"] = self.object.ferias.exclude(status="cancelada")[:6]
        ctx["rescisoes"] = self.object.rescisoes.exclude(status="cancelada")
        from django.utils import timezone

        from folha.custo import custo_funcionario

        ctx["custo"] = custo_funcionario(self.object)
        hoje = timezone.localdate()
        fim = self.object.data_desligamento or hoje
        dias = (fim - self.object.data_admissao).days
        ctx["tempo_casa"] = (dias // 365, (dias % 365) // 30)
        return ctx


class DesligamentoView(EmpresaRequiredMixin, UpdateView):
    model = Funcionario
    form_class = DesligamentoForm
    template_name = "form.html"
    extra_context = {
        "titulo": "Desligar funcionário",
        "aviso": "Ao salvar, o desligamento (S-2299) vai automaticamente para o eSocial. Atenção: o cálculo das "
                 "verbas rescisórias (TRCT) ainda não é feito por esta versão — calcule com o contador.",
    }

    def form_valid(self, form):
        resp = super().form_valid(form)
        if self.empresa.envio_automatico:
            try:
                gerar_desligamento(self.object)
            except ErroESocial as exc:
                messages.warning(self.request, str(exc))
                return resp
            messages.success(self.request, "Desligamento (S-2299) colocado na fila do eSocial.")
            if problema := tentar_processar(self.empresa):
                messages.warning(self.request, problema)
        return resp

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


class EscritorioMixin(EmpresaRequiredMixin, UserPassesTestMixin):
    """Só a equipe do escritório (is_staff), sempre na empresa ativa."""

    def test_func(self):
        return self.request.user.is_staff


class ExportarView(EscritorioMixin, View):
    TIPOS = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv; charset=utf-8",
    }

    def get(self, request):
        formato = "csv" if request.GET.get("formato") == "csv" else "xlsx"
        resp = HttpResponse(planilha.exportar(self.empresa, formato), content_type=self.TIPOS[formato])
        nome = f"funcionarios-{slugify(self.empresa.razao_social)}.{formato}"
        resp["Content-Disposition"] = f'attachment; filename="{nome}"'
        return resp


class ImportarView(EscritorioMixin, View):
    """Envia a planilha, mostra a prévia (nada gravado) e só grava quando a pessoa confirma."""

    template_name = "pessoal/importar.html"
    SESSAO = "importacao_funcionarios"
    LIMITE = 2 * 1024 * 1024

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        confirmar = "confirmar" in request.POST
        if confirmar:
            guardado = request.session.get(self.SESSAO)
            if not guardado or guardado["empresa"] != self.empresa.pk:
                messages.error(request, "A importação expirou ou a empresa ativa mudou. Envie o arquivo de novo.")
                return redirect("pessoal:importar")
            conteudo, nome, ja_no_esocial = base64.b64decode(guardado["conteudo"]), guardado["nome"], guardado["ja_no_esocial"]
        else:
            arquivo = request.FILES.get("arquivo")
            if arquivo is None or arquivo.size > self.LIMITE:
                messages.error(request, "Escolha uma planilha .xlsx ou .csv de até 2 MB.")
                return redirect("pessoal:importar")
            conteudo, nome, ja_no_esocial = arquivo.read(), arquivo.name, "ja_no_esocial" in request.POST
        try:
            linhas, ignoradas = planilha.analisar(conteudo, nome, self.empresa, ja_no_esocial)
        except planilha.ErroPlanilha as exc:
            messages.error(request, str(exc))
            return redirect("pessoal:importar")
        tem_erro = any(l.erros for l in linhas)
        if confirmar and not tem_erro:
            try:
                criados, atualizados = planilha.gravar(linhas)
            except IntegrityError:
                messages.error(request, "Nada foi gravado: duas pessoas ficariam com a mesma matrícula. Confira a planilha.")
                return redirect("pessoal:importar")
            del request.session[self.SESSAO]
            messages.success(request, f"Importação concluída: {criados} cadastrado(s) e {atualizados} atualizado(s). "
                                      "Nada foi enviado ao eSocial.")
            return redirect("pessoal:lista")
        request.session[self.SESSAO] = {
            "empresa": self.empresa.pk, "nome": nome, "ja_no_esocial": ja_no_esocial,
            "conteudo": base64.b64encode(conteudo).decode(),
        }
        return render(request, self.template_name, {
            "linhas": linhas, "ignoradas": ignoradas, "tem_erro": tem_erro, "nome_arquivo": nome,
            "resumo": {a: sum(l.acao == a and not l.erros for l in linhas) for a in ("criar", "atualizar", "igual")},
            "com_erro": sum(bool(l.erros) for l in linhas),
        })
