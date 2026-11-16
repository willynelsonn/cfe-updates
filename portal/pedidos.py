"""Pedidos da dona. Toda consulta filtra pela empresa dela: pedido ou anexo de outra empresa = 404."""

from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from empresas.acesso import eh_escritorio
from folha.custo import custo_mensal, liquido_estimado
from pessoal.models import Funcionario

from .anexos import anexar
from .models import Anexo, Mensagem, Pedido, concluir_os_aceitos
from .pedido_forms import FORMULARIOS, MensagemForm, dinheiro, resumo

DESCRICOES = {
    "contratei": "Alguém novo vai começar a trabalhar.",
    "sair": "Alguém pediu para sair ou vai ser dispensado.",
    "ferias": "Marcar as férias de alguém.",
    "alterar": "Endereço, celular, salário, função, banco ou Pix.",
    "documento": "Atestado, exame ou outro documento.",
    "duvida": "Pergunte ou mande um recado ao escritório.",
}


def da_dona(view):
    """Só a dona: o escritório vai para o painel; sem empresa ligada, volta ao início."""

    @login_required
    @wraps(view)
    def interna(request, *args, **kwargs):
        if eh_escritorio(request.user):
            return redirect("dashboard")
        if request.empresa is None:
            return redirect("portal:inicio")
        return view(request, *args, **kwargs)

    return interna


def tipos_permitidos(empresa) -> list[str]:
    if empresa.situacao == "ativa":
        return list(FORMULARIOS)
    return ["documento", "duvida"]  # em análise ou recusada: ainda não há equipe no sistema


def _pedido(request, pk, **filtros):
    return get_object_or_404(Pedido.objects.select_related("funcionario"), pk=pk, empresa=request.empresa, **filtros)


def baixar(anexo):
    return FileResponse(anexo.arquivo.open("rb"), as_attachment=True, filename=anexo.nome,
                        content_type=anexo.tipo_conteudo)


def _direitos_de_ferias(empresa):
    from folha.conformidade import proximo_periodo_aquisitivo

    hoje = timezone.localdate()
    linhas = []
    for f in Funcionario.objects.filter(empresa=empresa, data_desligamento__isnull=True).order_by("nome"):
        _, fim = proximo_periodo_aquisitivo(f, hoje)
        quando = fim + timedelta(days=1)
        linhas.append((f.nome, f"tem direito desde {quando:%d/%m/%Y}" if quando <= hoje
                       else f"terá direito a partir de {quando:%d/%m/%Y}"))
    return linhas


@da_dona
def lista(request):
    pedidos = Pedido.objects.filter(empresa=request.empresa)
    concluir_os_aceitos(pedidos)
    return render(request, "portal/pedidos.html", {"pedidos": pedidos.select_related("funcionario")})


@da_dona
def novo(request):
    permitidos = tipos_permitidos(request.empresa)
    tipos = [(t, rotulo, DESCRICOES[t]) for t, rotulo in Pedido.TIPOS if t in permitidos]
    return render(request, "portal/pedido_novo.html", {"tipos": tipos})


@da_dona
def criar(request, tipo):
    if tipo not in tipos_permitidos(request.empresa):
        raise Http404
    form = FORMULARIOS[tipo](request.POST or None, request.FILES or None, empresa=request.empresa)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            p = Pedido.objects.create(empresa=request.empresa, criado_por=request.user, tipo=tipo,
                                      respostas=form.respostas(), funcionario=form.cleaned_data.get("funcionario"))
            if arquivo := form.cleaned_data.get("arquivo"):
                anexar(p, arquivo, request.user)
        messages.success(request, "Pedido enviado. O escritório vai conferir e responder aqui.")
        return redirect("portal:pedido", pk=p.pk)
    return render(request, "portal/pedido_form.html", {
        "form": form, "titulo": dict(Pedido.TIPOS)[tipo],
        "direitos": _direitos_de_ferias(request.empresa) if tipo == "ferias" else None,
        "custo_url": reverse("portal:pedido_custo") if tipo == "contratei" else None,
    })


@da_dona
def custo(request):
    """Custo estimado de quem a dona quer contratar: pedaço de página que o formulário "Contratei" mostra."""
    if "contratei" not in tipos_permitidos(request.empresa):
        raise Http404
    try:
        salario = dinheiro("Salário").clean(request.GET.get("salario"))
    except ValidationError:
        return HttpResponse("")
    if not salario:
        return HttpResponse("")
    c = custo_mensal(request.empresa, salario)
    return render(request, "portal/_custo.html", {"custo": c, "liquido": liquido_estimado(salario, c.remuneracao)})


@da_dona
def pedido(request, pk):
    concluir_os_aceitos(Pedido.objects.filter(pk=pk, empresa=request.empresa))
    p = _pedido(request, pk)
    form = MensagemForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if p.situacao in ("concluido", "cancelado"):
            raise Http404
        if form.is_valid():
            with transaction.atomic():
                if texto := form.cleaned_data["texto"].strip():
                    Mensagem.objects.create(pedido=p, autor=request.user, texto=texto)
                if arquivo := form.cleaned_data.get("arquivo"):
                    anexar(p, arquivo, request.user)
                if p.situacao == "devolvido":  # a resposta da dona reenvia o pedido ao escritório
                    p.mudar("enviado", request.user)
            messages.success(request, "Mensagem enviada ao escritório.")
            return redirect("portal:pedido", pk=p.pk)
    return render(request, "portal/pedido.html", {
        "pedido": p, "resumo": resumo(p), "form": form, "mensagens": p.mensagens.select_related("autor"),
        "rota_anexo": "portal:pedido_anexo",
    })


@da_dona
def corrigir(request, pk):
    p = _pedido(request, pk, situacao="devolvido")
    form = FORMULARIOS[p.tipo](request.POST or None, request.FILES or None, empresa=request.empresa,
                               initial={**p.respostas, "funcionario": p.funcionario_id})
    if p.anexos.exists():
        form.fields["arquivo"].required = False  # o documento já foi mandado; outro é opcional
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            p.respostas = form.respostas()
            p.funcionario = form.cleaned_data.get("funcionario", p.funcionario)
            p.situacao = "enviado"
            p.save()
            if arquivo := form.cleaned_data.get("arquivo"):
                anexar(p, arquivo, request.user)
        messages.success(request, "Pedido corrigido e reenviado ao escritório.")
        return redirect("portal:pedido", pk=p.pk)
    return render(request, "portal/pedido_form.html", {"form": form, "titulo": f"Corrigir: {p.get_tipo_display()}",
                                                       "pedido": p, "custo_url": reverse("portal:pedido_custo")
                                                       if p.tipo == "contratei" else None})


@da_dona
@require_POST
def cancelar(request, pk):
    p = _pedido(request, pk, situacao__in=Pedido.ABERTOS)
    p.mudar("cancelado", None, "A dona cancelou o pedido.")
    messages.success(request, "Pedido cancelado.")
    return redirect("portal:pedidos")


@da_dona
def anexo(request, pk, anexo):
    return baixar(get_object_or_404(Anexo, pk=anexo, pedido_id=pk, pedido__empresa=request.empresa))
