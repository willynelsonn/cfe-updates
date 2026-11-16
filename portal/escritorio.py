"""Fila de pedidos do escritório. A dona nem chega aqui (PortalMiddleware); o decorador é a segunda tranca."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from empresas.acesso import eh_escritorio
from empresas.models import Empresa

from .anexos import anexar
from .models import Anexo, Mensagem, Pedido, concluir_os_aceitos
from .pedido_forms import MensagemForm, resumo
from .pedidos import baixar

# Pedidos que viram cadastro de verdade: aprovar abre o formulário técnico já usado pelo escritório.
DESTINO = {"contratei": "pessoal:novo", "ferias": "folha:ferias_nova", "sair": "folha:rescisao_nova",
           "alterar": "pessoal:editar"}
BOTAO_APROVAR = {"contratei": "Aprovar: abrir o cadastro do funcionário", "ferias": "Aprovar: abrir as férias",
                 "sair": "Aprovar: abrir a rescisão", "alterar": "Aprovar: abrir o cadastro para editar",
                 "documento": "Concluir (documento arquivado)", "duvida": "Concluir (dúvida respondida)"}
AVISOS = {"responder": "Mensagem enviada.", "devolver": "Pedido devolvido para a dona corrigir.",
          "cancelar": "Pedido cancelado."}


def do_escritorio(view):
    return login_required(user_passes_test(eh_escritorio)(view))


@do_escritorio
def lista(request):
    todos = Pedido.objects.select_related("empresa", "funcionario")
    concluir_os_aceitos(todos)
    ver = request.GET.get("ver")
    pedidos = todos if ver == "todos" else todos.filter(situacao__in=(*Pedido.ABERTOS, "aprovado"))
    return render(request, "pedidos/lista.html", {
        "pedidos": pedidos, "ver": ver, "novas_empresas": Empresa.objects.filter(situacao="em_analise"),
    })


@do_escritorio
def pedido(request, pk):
    concluir_os_aceitos(Pedido.objects.filter(pk=pk))
    p = get_object_or_404(Pedido.objects.select_related("empresa", "funcionario", "criado_por"), pk=pk)
    if p.situacao == "enviado":  # o escritório abriu: a dona passa a ver "Em análise"
        p.mudar("em_analise", request.user)
    form = MensagemForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        acao = request.POST.get("acao", "responder")
        if acao not in AVISOS or p.situacao in ("concluido", "cancelado") or (acao != "responder" and not p.aberto):
            raise Http404
        if form.is_valid():
            texto = form.cleaned_data["texto"].strip()
            if acao != "responder" and not texto:
                form.add_error("texto", "Escreva o motivo: a dona vai ler.")
            else:
                with transaction.atomic():
                    if arquivo := form.cleaned_data.get("arquivo"):
                        anexar(p, arquivo, request.user)
                    if acao == "responder":
                        if texto:
                            Mensagem.objects.create(pedido=p, autor=request.user, texto=texto)
                    else:
                        p.mudar({"devolver": "devolvido", "cancelar": "cancelado"}[acao], request.user, texto)
                messages.success(request, AVISOS[acao])
                return redirect("portal:escritorio_pedido", pk=p.pk)
    return render(request, "pedidos/detalhe.html", {
        "pedido": p, "resumo": resumo(p), "form": form, "mensagens": p.mensagens.select_related("autor"),
        "rota_anexo": "portal:escritorio_anexo", "botao_aprovar": BOTAO_APROVAR[p.tipo],
    })


@do_escritorio
@require_POST
def aprovar(request, pk):
    p = get_object_or_404(Pedido.objects.select_related("empresa"), pk=pk, situacao__in=Pedido.ABERTOS)
    if p.tipo not in DESTINO:  # documento e dúvida: nada vai ao governo
        p.mudar("concluido", request.user, "O escritório concluiu o pedido.")
        messages.success(request, "Pedido concluído.")
        return redirect("portal:escritorio_pedidos")
    if not p.empresa.ativa:
        messages.error(request, "A empresa deste pedido não está ativa. Libere a empresa antes de aprovar.")
        return redirect("portal:escritorio_pedido", pk=p.pk)
    if p.tipo == "alterar":
        if p.funcionario_id is None:
            messages.error(request, "A pessoa deste pedido não está mais no cadastro.")
            return redirect("portal:escritorio_pedido", pk=p.pk)
        url = reverse(DESTINO[p.tipo], args=[p.funcionario_id])
    else:
        url = reverse(DESTINO[p.tipo])
    # O formulário técnico trabalha na empresa ativa da sessão: passa a ser a do pedido.
    request.session["empresa_id"] = p.empresa_id
    return redirect(f"{url}?pedido={p.pk}")


@do_escritorio
def anexo(request, pk, anexo):
    return baixar(get_object_or_404(Anexo, pk=anexo, pedido_id=pk))
