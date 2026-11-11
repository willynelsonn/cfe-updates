from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from empresas.mixins import EmpresaRequiredMixin
from esocial.servico import (
    ErroESocial,
    data_pagamento_padrao,
    fechar_competencia,
    gerar_desligamento,
    gerar_ferias,
    tentar_processar,
)
from pessoal.models import Funcionario

from . import calculo as c
from .conformidade import problemas_ferias, proximo_periodo_aquisitivo
from .custo import aliquota_encargos, custo_mensal, custos_da_empresa
from .forms import CompetenciaForm, FechamentoForm, FeriasForm, LancamentoForm, RescisaoForm, RubricaForm
from .guias import atualizar_guias, emitir_darf
from .models import Competencia, Ferias, Guia, Holerite, Lancamento, Rescisao, Rubrica, criar_rubricas_padrao
from .rescisao import REGRAS, ErroRescisao, calcular_rescisao, problemas_rescisao
from .servico import ErroCalculo, calcular_competencia, calcular_ferias, resumo_encargos
from .tabelas import tabela_atualizada, tabelas_do_ano


# ---------------------------------------------------------------------------
# Rubricas
# ---------------------------------------------------------------------------
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
        "aviso": "O evento S-1010 da rubrica nova é gerado e enviado automaticamente na próxima apuração.",
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


# ---------------------------------------------------------------------------
# Competências
# ---------------------------------------------------------------------------
class CompetenciaListView(EmpresaRequiredMixin, ListView):
    model = Competencia
    template_name = "folha/competencias.html"


class CompetenciaCreateView(EmpresaRequiredMixin, CreateView):
    model = Competencia
    form_class = CompetenciaForm
    template_name = "form.html"
    extra_context = {
        "titulo": "Abrir folha do mês",
        "explicacao": "Escolha o mês trabalhado e a data em que o salário será pago. Em novembro, informe também "
                      "a data da 1ª parcela do 13º (até 30/11) para calculá-la junto.",
    }

    def get_initial(self):
        hoje = timezone.localdate()
        ini = {
            "ano": hoje.year, "mes": hoje.month,
            "data_pagamento": data_pagamento_padrao(hoje.year, hoje.month, self.empresa.dia_pagamento),
        }
        if hoje.month == 11:
            ini["data_adiantamento_13"] = c.dia_util_anterior(date(hoje.year, 11, 30))
        return ini

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["empresa"] = self.empresa
        return kw

    def form_valid(self, form):
        form.instance.empresa = self.empresa
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("folha:competencia", args=[self.object.pk])


class CompetenciaUpdateView(EmpresaRequiredMixin, UpdateView):
    model = Competencia
    form_class = CompetenciaForm
    template_name = "form.html"
    extra_context = {"titulo": "Datas da folha"}

    def get_queryset(self):
        return super().get_queryset().filter(tipo="mensal").exclude(status="fechada")

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["empresa"] = self.empresa
        return kw

    def form_valid(self, form):
        form.instance.status = "aberta"
        messages.success(self.request, "Datas atualizadas. Calcule a folha novamente.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("folha:competencia", args=[self.object.pk])


def _competencia(request, pk) -> Competencia:
    if request.empresa is None:
        raise Http404
    return get_object_or_404(Competencia, pk=pk, empresa=request.empresa)


@login_required
def competencia(request, pk):
    comp = _competencia(request, pk)
    holerites = list(comp.holerites.select_related("funcionario", "ferias"))
    eventos = list(comp.evento_set.all())
    if comp.status != "aberta":
        atualizar_guias(comp)
    status_ev = {e.status for e in eventos}
    etapa = 1
    if comp.status == "calculada":
        etapa = 2
    elif comp.status == "fechada":
        etapa = 4 if eventos and status_ev <= {"aceito"} else 3
    ctx = {
        "c": comp,
        "etapa": etapa,
        "form_lancamento": LancamentoForm(competencia=comp) if not comp.decimo_terceiro else None,
        "lancamentos": comp.lancamentos.select_related("funcionario", "rubrica"),
        "holerites": holerites,
        "resumo": resumo_encargos(comp) if holerites else None,
        "form_fechamento": FechamentoForm(),
        "tabela": tabelas_do_ano(comp.ano),
        "tabela_atualizada": tabela_atualizada(comp.ano),
        "eventos": eventos,
        "eventos_aceitos": sum(1 for e in eventos if e.status == "aceito"),
        "eventos_problema": [e for e in eventos if e.corrigivel],
        "guias": comp.guias.all(),
        "ferias_mes": Ferias.objects.filter(
            funcionario__empresa=comp.empresa, status="calculada",
            data_pagamento__year=comp.ano, data_pagamento__month=comp.mes,
        ) if not comp.decimo_terceiro else [],
    }
    return render(request, "folha/competencia.html", ctx)


@login_required
@require_POST
def novo_lancamento(request, pk):
    comp = _competencia(request, pk)
    if not comp.editavel:
        messages.error(request, "Folha fechada: não aceita novos lançamentos.")
        return redirect("folha:competencia", pk=pk)
    form = LancamentoForm(request.POST, competencia=comp)
    if form.is_valid():
        form.instance.competencia = comp
        form.save()
        comp.status = "aberta"
        comp.save(update_fields=["status"])
        messages.success(request, "Lançamento incluído. Clique em Calcular para atualizar os holerites.")
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
        comp.status = "aberta"
        comp.save(update_fields=["status"])
        messages.success(request, "Lançamento excluído. Calcule de novo.")
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
        messages.success(request, f"Cálculo pronto: {comp.holerites.count()} demonstrativo(s). Confira e envie.")
        for aviso in avisos:
            messages.warning(request, aviso)
    return redirect("folha:competencia", pk=pk)


def _fechar_e_enviar(request, comp, transmitir_dctfweb=True):
    try:
        eventos = fechar_competencia(comp, transmitir_dctfweb=transmitir_dctfweb)
    except ErroESocial as exc:
        messages.error(request, str(exc))
        return False
    com_erro = [e for e in eventos if e.status == "erro"]
    messages.success(request, f"Folha fechada: {len(eventos)} evento(s) do eSocial na fila de envio.")
    if com_erro:
        messages.error(request, f"{len(com_erro)} evento(s) com erro de validação — veja abaixo.")
    if problema := tentar_processar(comp.empresa):
        messages.warning(request, problema)
    atualizar_guias(comp)
    return True


@login_required
@require_POST
def fechar(request, pk):
    comp = _competencia(request, pk)
    form = FechamentoForm(request.POST)
    form.is_valid()
    _fechar_e_enviar(request, comp, form.cleaned_data.get("transmitir_dctfweb", False))
    return redirect("folha:competencia", pk=pk)


@login_required
@require_POST
def apurar(request, pk):
    """Botão único: calcula, fecha e envia ao eSocial."""
    comp = _competencia(request, pk)
    if comp.status == "fechada":
        messages.info(request, "Esta folha já foi apurada e enviada.")
        return redirect("folha:competencia", pk=pk)
    try:
        avisos = calcular_competencia(comp)
    except ErroCalculo as exc:
        messages.error(request, str(exc))
        return redirect("folha:competencia", pk=pk)
    for aviso in avisos:
        messages.warning(request, aviso)
    if avisos and request.POST.get("ignorar_avisos") != "1":
        messages.info(request, "A folha foi calculada, mas há avisos. Confira e clique em “Enviar ao eSocial”.")
        return redirect("folha:competencia", pk=pk)
    _fechar_e_enviar(request, comp, request.POST.get("transmitir_dctfweb", "1") == "1")
    return redirect("folha:competencia", pk=pk)


# ---------------------------------------------------------------------------
# Holerites
# ---------------------------------------------------------------------------
def _dados_holerite(hol):
    itens = hol.itens.select_related("rubrica")
    return {
        "h": hol,
        "proventos": [i for i in itens if i.rubrica.tipo == 1],
        "descontos": [i for i in itens if i.rubrica.tipo == 2],
    }


@login_required
def holerite(request, pk):
    hol = get_object_or_404(
        Holerite.objects.select_related("funcionario__cargo", "competencia__empresa"),
        pk=pk, competencia__empresa=request.empresa,
    )
    return render(request, "folha/holerite.html", _dados_holerite(hol))


@login_required
def holerites_impressao(request, pk):
    comp = _competencia(request, pk)
    lista = [_dados_holerite(h) for h in comp.holerites.select_related("funcionario__cargo", "competencia__empresa")]
    return render(request, "folha/holerites_lote.html", {"lista": lista, "comp": comp})


# ---------------------------------------------------------------------------
# 13º salário
# ---------------------------------------------------------------------------
@login_required
def decimo_terceiro(request):
    """Abre (ou mostra) a apuração da 2ª parcela do 13º do ano."""
    if request.empresa is None:
        return redirect("empresas:nova")
    ano = int(request.GET.get("ano") or timezone.localdate().year)
    comp = Competencia.objects.filter(empresa=request.empresa, tipo="13", ano=ano).first()
    if comp:
        return redirect("folha:competencia", pk=comp.pk)
    if request.method == "POST":
        comp = Competencia.objects.create(
            empresa=request.empresa, tipo="13", ano=ano, mes=12,
            data_pagamento=c.dia_util_anterior(date(ano, 12, 20)),
        )
        messages.success(request, f"13º salário de {ano} aberto. Pagamento previsto em {comp.data_pagamento:%d/%m/%Y}.")
        return redirect("folha:competencia", pk=comp.pk)
    return render(request, "folha/decimo_terceiro.html", {"ano": ano})


# ---------------------------------------------------------------------------
# Férias
# ---------------------------------------------------------------------------
class FeriasListView(EmpresaRequiredMixin, ListView):
    model = Ferias
    template_name = "folha/ferias_lista.html"

    def get_queryset(self):
        return Ferias.objects.filter(funcionario__empresa=self.empresa).select_related("funcionario")


@login_required
def ferias_nova(request):
    if request.empresa is None:
        return redirect("empresas:nova")
    initial = {}
    if fid := request.GET.get("funcionario"):
        func = get_object_or_404(Funcionario, pk=fid, empresa=request.empresa)
        ini, fim = proximo_periodo_aquisitivo(func, timezone.localdate())
        initial = {"funcionario": func, "aquisitivo_inicio": ini, "aquisitivo_fim": fim, "dias": 30}
    form = FeriasForm(request.POST or None, empresa=request.empresa, initial=initial)
    if request.method == "POST" and form.is_valid():
        fe = form.save()
        calcular_ferias(fe)
        messages.success(request, f"Férias calculadas: líquido de R$ {fe.liquido} a pagar até "
                                  f"{fe.data_pagamento:%d/%m/%Y}.")
        empresa = request.empresa
        if empresa.envio_automatico:
            try:
                gerar_ferias(fe)
            except ErroESocial as exc:
                messages.warning(request, str(exc))
            if problema := tentar_processar(empresa):
                messages.warning(request, problema)
            else:
                messages.info(request, "O aviso de férias (S-2230) foi para a fila do eSocial.")
        return redirect("folha:ferias_detalhe", pk=fe.pk)
    return render(request, "folha/ferias_form.html", {"form": form})


@login_required
def ferias_detalhe(request, pk):
    fe = get_object_or_404(Ferias.objects.select_related("funcionario__cargo", "funcionario__empresa"),
                           pk=pk, funcionario__empresa=request.empresa)
    return render(request, "folha/ferias_detalhe.html", {
        "fe": fe, "problemas": problemas_ferias(fe), "eventos": fe.evento_set.all(),
        "abono_valor": fe.valor_abono,
    })


@login_required
def ferias_documento(request, pk, doc):
    fe = get_object_or_404(Ferias.objects.select_related("funcionario__cargo", "funcionario__empresa"),
                           pk=pk, funcionario__empresa=request.empresa)
    if doc not in {"aviso", "recibo"}:
        raise Http404
    return render(request, f"folha/ferias_{doc}.html", {"fe": fe})


@login_required
@require_POST
def ferias_cancelar(request, pk):
    fe = get_object_or_404(Ferias, pk=pk, funcionario__empresa=request.empresa)
    if Holerite.objects.filter(ferias=fe, competencia__status="fechada").exists():
        messages.error(request, "Estas férias já entraram numa folha fechada e enviada; cancele com o contador.")
    else:
        fe.status = "cancelada"
        fe.save(update_fields=["status"])
        fe.evento_set.filter(status__in=["pendente", "erro", "rejeitado"]).delete()
        messages.success(request, "Férias canceladas.")
    return redirect("folha:ferias")


# ---------------------------------------------------------------------------
# Guias
# ---------------------------------------------------------------------------
@login_required
def guias(request, pk):
    comp = _competencia(request, pk)
    from esocial import integra_contador

    return render(request, "folha/guias.html", {
        "c": comp, "guias": atualizar_guias(comp), "resumo": resumo_encargos(comp) if comp.holerites.exists() else None,
        "integra": integra_contador.configurado(),
    })


@login_required
@require_POST
def gerar_guias(request, pk):
    comp = _competencia(request, pk)
    if problema := tentar_processar(comp.empresa):
        messages.warning(request, problema)
    lista = atualizar_guias(comp)
    if not lista:
        messages.error(request, "Calcule a folha antes de gerar as guias.")
        return redirect("folha:competencia", pk=pk)
    for g in lista:
        if g.tipo == "darf" and g.status in {"disponivel", "erro"}:
            emitir_darf(g)
    prontas = [g for g in lista if g.status in {"disponivel", "emitida"}]
    if prontas:
        messages.success(request, "Guias atualizadas. Veja abaixo como pagar cada uma.")
    else:
        messages.info(request, "As guias ficam prontas quando o eSocial aceitar o fechamento da folha (S-1299).")
    return redirect("folha:guias", pk=pk)


@login_required
def guia_pdf(request, pk):
    g = get_object_or_404(Guia, pk=pk, empresa=request.empresa)
    if not g.pdf:
        raise Http404
    resp = HttpResponse(bytes(g.pdf), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{g.tipo}_{g.competencia.per_apur}.pdf"'
    return resp


@login_required
@require_POST
def guia_paga(request, pk):
    g = get_object_or_404(Guia, pk=pk, empresa=request.empresa)
    g.status = "paga"
    g.save(update_fields=["status", "atualizada_em"])
    messages.success(request, f"{g.get_tipo_display()} marcada como paga.")
    return redirect("folha:guias", pk=g.competencia_id)


# ---------------------------------------------------------------------------
# Rescisão
# ---------------------------------------------------------------------------


class RescisaoListView(EmpresaRequiredMixin, ListView):
    model = Rescisao
    template_name = "folha/rescisoes.html"

    def get_queryset(self):
        return Rescisao.objects.filter(funcionario__empresa=self.empresa).select_related("funcionario")


@login_required
def rescisao_nova(request):
    if request.empresa is None:
        return redirect("empresas:nova")
    initial = {"data_desligamento": timezone.localdate(), "data_aviso": timezone.localdate()}
    if fid := request.GET.get("funcionario"):
        initial["funcionario"] = get_object_or_404(Funcionario, pk=fid, empresa=request.empresa)
    form = RescisaoForm(request.POST or None, empresa=request.empresa, initial=initial)
    if request.method == "POST" and form.is_valid():
        resc = form.save()
        try:
            calcular_rescisao(resc)
        except ErroRescisao as exc:
            resc.delete()
            messages.error(request, str(exc))
            return render(request, "folha/rescisao_form.html", {"form": form, "regras": REGRAS})
        messages.success(request, f"Rescisão calculada: líquido de R$ {resc.liquido} a pagar até "
                                  f"{resc.data_pagamento:%d/%m/%Y}.")
        if request.empresa.envio_automatico:
            try:
                gerar_desligamento(resc.funcionario)
            except ErroESocial as exc:
                messages.warning(request, str(exc))
            else:
                messages.info(request, "O desligamento (S-2299) com as verbas foi para a fila do eSocial.")
            if problema := tentar_processar(request.empresa):
                messages.warning(request, problema)
        return redirect("folha:rescisao_detalhe", pk=resc.pk)
    return render(request, "folha/rescisao_form.html", {"form": form, "regras": REGRAS})


def _rescisao(request, pk):
    return get_object_or_404(Rescisao.objects.select_related("funcionario__cargo", "funcionario__empresa"),
                             pk=pk, funcionario__empresa=request.empresa)


@login_required
def rescisao_detalhe(request, pk):
    resc = _rescisao(request, pk)
    return render(request, "folha/rescisao_detalhe.html", {
        "r": resc, "regra": REGRAS.get(resc.motivo), "problemas": problemas_rescisao(resc),
        "proventos": [i for i in resc.itens if i["tipo"] == "provento"],
        "descontos": [i for i in resc.itens if i["tipo"] == "desconto"],
        "eventos": resc.funcionario.evento_set.filter(tipo="S-2299"),
    })


@login_required
def rescisao_trct(request, pk):
    resc = _rescisao(request, pk)
    return render(request, "folha/rescisao_trct.html", {
        "r": resc, "regra": REGRAS.get(resc.motivo),
        "proventos": [i for i in resc.itens if i["tipo"] == "provento"],
        "descontos": [i for i in resc.itens if i["tipo"] == "desconto"],
    })


@login_required
@require_POST
def rescisao_cancelar(request, pk):
    resc = _rescisao(request, pk)
    if resc.funcionario.evento_set.filter(tipo="S-2299", status__in=["enviado", "aceito"]).exists():
        messages.error(request, "O desligamento já foi enviado ao eSocial; a reversão precisa de exclusão (S-3000) "
                                "com o contador.")
        return redirect("folha:rescisao_detalhe", pk=pk)
    resc.status = "cancelada"
    resc.save(update_fields=["status"])
    f = resc.funcionario
    f.data_desligamento = None
    f.motivo_desligamento = ""
    f.aviso_previo_indenizado = False
    f.save(update_fields=["data_desligamento", "motivo_desligamento", "aviso_previo_indenizado", "atualizado_em"])
    f.evento_set.filter(tipo="S-2299", status__in=["pendente", "erro", "rejeitado"]).delete()
    messages.success(request, "Rescisão cancelada; o funcionário voltou a ficar ativo.")
    return redirect("pessoal:detalhe", pk=f.pk)


# ---------------------------------------------------------------------------
# Custos
# ---------------------------------------------------------------------------


@login_required
def custos(request):
    if request.empresa is None:
        return redirect("empresas:nova")
    lista = custos_da_empresa(request.empresa)
    total = sum((cu.total for _, cu in lista), Decimal("0"))
    simulacao = None
    salario_sim = request.GET.get("salario", "").replace(".", "").replace(",", ".")
    if salario_sim:
        try:
            valor = Decimal(salario_sim)
            if valor > 0:
                simulacao = custo_mensal(
                    request.empresa, valor, vale_transporte=Decimal(request.GET.get("vt") or 0),
                    beneficios=Decimal(request.GET.get("beneficios") or 0),
                    periculosidade=bool(request.GET.get("periculosidade")),
                )
        except InvalidOperation:
            messages.error(request, "Informe o salário em reais, ex.: 2500,00.")
    aliq, partes = aliquota_encargos(request.empresa)
    return render(request, "folha/custos.html", {
        "lista": lista, "total": total, "anual": total * 12, "simulacao": simulacao,
        "aliq_encargos": aliq, "partes_encargos": partes,
        "media": (total / len(lista)) if lista else Decimal("0"),
    })


# ---------------------------------------------------------------------------
# Relatórios
# ---------------------------------------------------------------------------
def _filtros_relatorio(request, tipo):
    from .relatorios import Filtros

    hoje = timezone.localdate()
    empresa = request.empresa
    comps = Competencia.objects.filter(empresa=empresa, holerites__isnull=False).distinct()
    f = Filtros()
    pk = request.GET.get("competencia")
    if pk and pk.isdigit():
        f.competencia = comps.filter(pk=pk).first()
    if f.competencia is None and "competencia" in tipo.filtros:
        f.competencia = comps.filter(tipo="mensal").first() or comps.first()

    def inteiro(nome, padrao, minimo, maximo):
        try:
            valor = int(request.GET.get(nome, padrao))
        except ValueError:
            return padrao
        return valor if minimo <= valor <= maximo else padrao

    f.ano = inteiro("ano", f.competencia.ano if f.competencia else hoje.year, 2000, 2100)
    padrao_mes = 0 if "mes_opcional" in tipo.filtros else hoje.month
    f.mes = inteiro("mes", padrao_mes, 0 if "mes_opcional" in tipo.filtros else 1, 12)
    fpk = request.GET.get("funcionario")
    if fpk and fpk.isdigit():
        f.funcionario = Funcionario.objects.filter(empresa=empresa, pk=fpk).first()
    if request.GET.get("situacao") in {"ativos", "desligados", "todos"}:
        f.situacao = request.GET["situacao"]
    return f, comps


@login_required
def relatorios(request):
    from .relatorios import GRUPOS, RELATORIOS

    if request.empresa is None:
        return redirect("empresas:nova")
    grupos = [(g, [t for t in RELATORIOS if t.grupo == g]) for g in GRUPOS]
    ultima = Competencia.objects.filter(empresa=request.empresa, holerites__isnull=False).distinct().first()
    return render(request, "folha/relatorios.html", {"grupos": grupos, "ultima": ultima})


@login_required
def relatorio(request, slug):
    from .relatorios import MESES, POR_SLUG, para_csv

    if request.empresa is None:
        return redirect("empresas:nova")
    tipo = POR_SLUG.get(slug)
    if tipo is None:
        raise Http404
    f, comps = _filtros_relatorio(request, tipo)
    rel = tipo.funcao(request.empresa, f)
    if request.GET.get("formato") == "csv":
        resp = HttpResponse(para_csv(rel, request.empresa), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{slug}-{timezone.localdate():%Y%m%d}.csv"'
        return resp
    hoje = timezone.localdate()
    return render(request, "folha/relatorio.html", {
        "tipo": tipo, "rel": rel, "f": f, "competencias": comps,
        "anos": range(hoje.year + 1, max(hoje.year - 8, 2000) - 1, -1),
        "meses": list(enumerate(MESES))[1:],
        "funcionarios": Funcionario.objects.filter(empresa=request.empresa).order_by("nome"),
        "query_csv": _query_com(request, formato="csv"),
        "gerado_em": timezone.localtime(),
    })


def _query_com(request, **extra):
    q = request.GET.copy()
    for k, v in extra.items():
        q[k] = v
    return q.urlencode()
