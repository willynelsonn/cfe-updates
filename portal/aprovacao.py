"""Aprovar um pedido = salvar o formulário técnico do escritório aberto com ?pedido=<id>.

O pedido só é usado se for do escritório, da empresa ativa da sessão, do tipo da tela e ainda aberto.
"""

from django.contrib import messages
from django.utils import timezone

from empresas.acesso import eh_escritorio

from .models import Mensagem, Pedido
from .pedido_forms import resumo

MOTIVO = {"pessoa": "07", "empresa": "02", "acordo": "33", "fim_contrato": "06", "justa_causa": "01"}


def pedido_em_aberto(request, tipo: str, **filtros):
    pk = request.GET.get("pedido", "")
    if not (pk.isdigit() and eh_escritorio(request.user) and request.empresa):
        return None
    return Pedido.objects.filter(pk=pk, tipo=tipo, empresa=request.empresa, situacao__in=Pedido.ABERTOS,
                                 **filtros).select_related("funcionario").first()


def _aviso_previo(r: dict):
    if r.get("quem_pediu") in ("fim_contrato", "justa_causa"):
        return "nenhum"
    if r.get("aviso") == "trabalha":
        return "trabalhado"
    if r.get("aviso") == "nao_trabalha":
        return "dispensado" if r.get("quem_pediu") == "pessoa" else "indenizado"
    return None


def iniciais(pedido) -> dict:
    """O que dá para preencher no formulário técnico a partir das respostas da dona."""
    r = pedido.respostas
    if pedido.tipo == "contratei":
        d = {c: r.get(c) for c in ("nome", "cpf", "data_nascimento", "telefone", "email", "cep", "salario")}
        d.update(data_admissao=r.get("data_inicio"), descricao_jornada=r.get("horario"))
    elif pedido.tipo == "sair":
        d = {"funcionario": pedido.funcionario_id, "motivo": MOTIVO.get(r.get("quem_pediu")),
             "tipo_aviso": _aviso_previo(r), "data_desligamento": r.get("ultimo_dia")}
    elif pedido.tipo == "ferias":
        d = {"funcionario": pedido.funcionario_id, "inicio": r.get("inicio"), "dias": r.get("dias"),
             "dias_abono": 10 if r.get("vender_10") else 0}
        if pedido.funcionario:
            from folha.conformidade import proximo_periodo_aquisitivo

            d["aquisitivo_inicio"], d["aquisitivo_fim"] = proximo_periodo_aquisitivo(pedido.funcionario,
                                                                                     timezone.localdate())
    else:  # alterar: endereço, função e banco/Pix não têm campo único; ficam no resumo ao lado
        d = {c: r.get(c) for c in ("cep", "telefone", "salario")}
    return {k: v for k, v in d.items() if v not in (None, "")}


def contexto(pedido) -> dict:
    return {"pedido": pedido, "resumo_pedido": resumo(pedido)} if pedido else {}


def aprovar(request, pedido, **vinculo) -> None:
    for campo, valor in vinculo.items():
        setattr(pedido, campo, valor)
    alterar = pedido.tipo == "alterar"  # S-2205/S-2206 ainda não existem: nada a esperar do eSocial
    pedido.situacao = "concluido" if alterar else "aprovado"
    pedido.save()
    Mensagem.objects.create(pedido=pedido, texto="O escritório aprovou e atualizou o cadastro." if alterar else
                            "O escritório aprovou. Quando o eSocial aceitar, o pedido fica concluído.")
    messages.success(request, f"Pedido nº {pedido.pk} da cliente aprovado.")


class PedidoMixin:
    """Telas técnicas (CBV): ?pedido=<id> preenche o formulário e, ao salvar, aprova o pedido."""

    tipo_pedido = ""

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        filtros = {"funcionario_id": kwargs["pk"]} if "pk" in kwargs else {}
        self.pedido = pedido_em_aberto(request, self.tipo_pedido, **filtros)

    def get_initial(self):
        return {**super().get_initial(), **(iniciais(self.pedido) if self.pedido else {})}

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), **contexto(self.pedido)}

    def aprovar_pedido(self):
        if self.pedido:
            aprovar(self.request, self.pedido, funcionario=self.object)
