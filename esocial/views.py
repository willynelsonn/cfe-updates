from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from empresas.mixins import EmpresaRequiredMixin
from pessoal.models import Funcionario

from .assinatura import ErroCertificado
from .models import Evento, Lote
from .servico import (
    ErroESocial,
    consultar_lotes_enviados,
    gerar_admissao,
    gerar_desligamento,
    gerar_eventos_iniciais,
    reenviar,
    transmitir_pendentes,
)


class EventoListView(EmpresaRequiredMixin, ListView):
    model = Evento
    template_name = "esocial/eventos.html"
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset().select_related("funcionario", "lote")
        if status := self.request.GET.get("status"):
            qs = qs.filter(status=status)
        if tipo := self.request.GET.get("tipo"):
            qs = qs.filter(tipo=tipo)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_choices"] = Evento.STATUS
        ctx["pendentes"] = Evento.objects.filter(empresa=self.empresa, status="pendente").count()
        ctx["aguardando"] = Lote.objects.filter(empresa=self.empresa, status="enviado").count()
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
    eventos = _executar(request, lambda: gerar_eventos_iniciais(request.empresa),
                        lambda evs: f"{len(evs)} eventos iniciais gerados (S-1000, S-1005, S-1020 e S-1010).")
    if eventos and any(e.status == "erro" for e in eventos):
        messages.error(request, "Há eventos com erro de validação: confira a lista.")
    return redirect("esocial:eventos")


@login_required
@require_POST
def admissao(request, pk):
    func = get_object_or_404(Funcionario, pk=pk, empresa=request.empresa)
    ev = _executar(request, lambda: gerar_admissao(func), lambda e: f"S-2200 de {func.nome} gerado.")
    if ev and ev.status == "erro":
        messages.error(request, "O S-2200 tem erros de validação: " + "; ".join(ev.mensagens))
    return redirect("pessoal:detalhe", pk=pk)


@login_required
@require_POST
def desligamento(request, pk):
    func = get_object_or_404(Funcionario, pk=pk, empresa=request.empresa)
    ev = _executar(request, lambda: gerar_desligamento(func), lambda e: f"S-2299 de {func.nome} gerado.")
    if ev and ev.status == "erro":
        messages.error(request, "O S-2299 tem erros de validação: " + "; ".join(ev.mensagens))
    return redirect("pessoal:detalhe", pk=pk)


@login_required
@require_POST
def transmitir(request):
    lotes = _executar(request, lambda: transmitir_pendentes(request.empresa),
                      lambda ls: f"{len(ls)} lote(s) transmitido(s). Aguarde alguns minutos e clique em Consultar.")
    for lote in lotes or []:
        if lote.status in {"erro", "rejeitado"}:
            messages.error(request, f"Lote {lote.pk}: {lote.cd_resposta} {lote.desc_resposta}")
    return redirect("esocial:eventos")


@login_required
@require_POST
def consultar(request):
    _executar(request, lambda: consultar_lotes_enviados(request.empresa),
              lambda ls: f"{len(ls)} lote(s) consultado(s).")
    return redirect("esocial:eventos")


@login_required
@require_POST
def reenviar_evento(request, pk):
    ev = get_object_or_404(Evento, pk=pk, empresa=request.empresa)
    reenviar(ev)
    messages.success(request, "Evento voltou para a fila de envio.")
    return redirect("esocial:evento", pk=pk)


@login_required
def guia(request):
    return render(request, "esocial/guia.html")
