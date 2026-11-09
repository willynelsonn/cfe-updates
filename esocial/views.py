from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from empresas.mixins import EmpresaRequiredMixin
from pessoal.models import Funcionario

from .assinatura import ErroCertificado
from .models import Evento, Lote
from .servico import (
    ErroESocial,
    gerar_admissao,
    gerar_desligamento,
    processar_fila,
    reenviar,
    regerar,
    situacao_fila,
    sincronizar_tabelas,
)


class EventoListView(EmpresaRequiredMixin, ListView):
    model = Evento
    template_name = "esocial/eventos.html"
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset().select_related("funcionario", "lote")
        if status := self.request.GET.get("status"):
            qs = qs.filter(status__in=["erro", "rejeitado"]) if status == "rejeitado" else qs.filter(status=status)
        if tipo := self.request.GET.get("tipo"):
            qs = qs.filter(tipo=tipo)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_choices"] = Evento.STATUS
        ctx["fila"] = situacao_fila(self.empresa)
        return ctx


class EventoDetailView(EmpresaRequiredMixin, DetailView):
    model = Evento
    template_name = "esocial/evento.html"


class LoteListView(EmpresaRequiredMixin, ListView):
    model = Lote
    template_name = "esocial/lotes.html"
    paginate_by = 50


@login_required
def baixar_xml(request, pk):
    ev = get_object_or_404(Evento, pk=pk, empresa=request.empresa)
    resp = HttpResponse(ev.xml_assinado or ev.xml, content_type="application/xml")
    resp["Content-Disposition"] = f'attachment; filename="{ev.tipo}_{ev.id_evento}.xml"'
    return resp


def _executar(request, acao, sucesso):
    try:
        resultado = acao()
    except (ErroESocial, ErroCertificado) as exc:
        messages.error(request, str(exc))
        return None
    messages.success(request, sucesso(resultado))
    return resultado


@login_required
@require_POST
def gerar_iniciais(request):
    eventos = _executar(request, lambda: sincronizar_tabelas(request.empresa),
                        lambda evs: f"{len(evs)} evento(s) de cadastro da empresa e rubricas na fila."
                        if evs else "Os cadastros da empresa e das rubricas já estão no eSocial (ou na fila).")
    if eventos and any(e.status == "erro" for e in eventos):
        messages.error(request, "Há eventos com erro de validação: confira a lista.")
    return redirect("esocial:eventos")


@login_required
@require_POST
def admissao(request, pk):
    func = get_object_or_404(Funcionario, pk=pk, empresa=request.empresa)
    ev = _executar(request, lambda: gerar_admissao(func), lambda e: f"Admissão de {func.nome} na fila do eSocial.")
    if ev and ev.status == "erro":
        messages.error(request, "A admissão tem erros de validação: " + "; ".join(ev.mensagens))
    return redirect("pessoal:detalhe", pk=pk)


@login_required
@require_POST
def desligamento(request, pk):
    func = get_object_or_404(Funcionario, pk=pk, empresa=request.empresa)
    ev = _executar(request, lambda: gerar_desligamento(func),
                   lambda e: f"Desligamento de {func.nome} na fila do eSocial.")
    if ev and ev.status == "erro":
        messages.error(request, "O desligamento tem erros de validação: " + "; ".join(ev.mensagens))
    return redirect("pessoal:detalhe", pk=pk)


@login_required
@require_POST
def transmitir(request):
    _executar(request, lambda: processar_fila(request.empresa),
              lambda r: f"{r['lotes_enviados']} lote(s) enviado(s), {r['consultados']} retorno(s) consultado(s). "
                        f"Na fila: {r['pendentes']} · aguardando governo: {r['enviados']}.")
    return redirect(request.POST.get("next") or "esocial:eventos")


consultar = transmitir  # o mesmo passo consulta retornos e envia o que ficou liberado


@login_required
@require_POST
def processar_json(request):
    """Chamado pela tela a cada poucos segundos enquanto houver algo em andamento."""
    try:
        resultado = processar_fila(request.empresa)
    except (ErroESocial, ErroCertificado) as exc:
        return JsonResponse({"erro": str(exc), **situacao_fila(request.empresa)}, status=200)
    return JsonResponse(resultado)


@login_required
def situacao_json(request):
    return JsonResponse(situacao_fila(request.empresa) if request.empresa else {})


@login_required
@require_POST
def reenviar_evento(request, pk):
    ev = get_object_or_404(Evento, pk=pk, empresa=request.empresa)
    reenviar(ev)
    messages.success(request, "Evento voltou para a fila de envio sem alterações.")
    return redirect("esocial:evento", pk=pk)


@login_required
@require_POST
def regerar_evento(request, pk):
    ev = get_object_or_404(Evento, pk=pk, empresa=request.empresa)
    novo = _executar(request, lambda: regerar(ev), lambda e: "Evento gerado de novo com os dados atuais do cadastro.")
    return redirect("esocial:evento", pk=novo.pk) if novo else redirect("esocial:evento", pk=pk)


@login_required
def guia(request):
    return render(request, "esocial/guia.html")
