from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render

from config.seguranca import ip_do_cliente
from empresas.acesso import eh_escritorio
from empresas.models import Acesso, Empresa
from empresas.validators import formatar_cnpj

from .forms import TERMOS_VERSAO, CadastroForm


@login_required
def inicio(request):
    if eh_escritorio(request.user):
        return redirect("dashboard")
    return render(request, "portal/inicio.html", {
        "empresa": request.empresa,
        "escritorio_cnpj": formatar_cnpj(settings.FOLHA_ESCRITORIO_CNPJ),
        "escritorio_nome": settings.FOLHA_ESCRITORIO_NOME,
    })


def _passou_do_limite(request) -> bool:
    """Conta cada envio do cadastro por IP; acima do limite em 1 hora, bloqueia."""
    chave = f"cadastro:ip:{ip_do_cliente(request)}"
    tentativas = cache.get(chave, 0) + 1
    cache.set(chave, tentativas, 3600)
    return tentativas > settings.CADASTRO_MAX_POR_HORA


def _criar_cadastro(d: dict, cnpj: dict) -> User:
    primeiro, _, resto = d["nome"].strip().partition(" ")
    with transaction.atomic():
        usuario = User.objects.create_user(d["email"], email=d["email"], password=d["senha1"],
                                           first_name=primeiro[:150], last_name=resto.strip()[:150])
        empresa = Empresa.objects.create(
            razao_social=cnpj.get("razao_social") or d["razao_social"].strip(),
            nome_fantasia=cnpj.get("nome_fantasia", ""), nr_insc=d["cnpj"], cnae=cnpj.get("cnae", ""),
            municipio=cnpj.get("municipio", ""), uf=cnpj.get("uf", ""), funcionarios_informados=d["funcionarios"],
            situacao="em_analise", ativa=False, envio_automatico=False,
        )
        Acesso.objects.create(usuario=usuario, empresa=empresa, termos_versao=TERMOS_VERSAO,
                              cpf=d["cpf"], celular=d["celular"].strip())
    return usuario


def cadastro(request):
    if request.user.is_authenticated:
        return redirect("portal:inicio")
    if request.method != "POST":
        return render(request, "portal/cadastro.html", {"form": CadastroForm()})
    if _passou_do_limite(request):
        form = CadastroForm(initial=request.POST.dict())
        return render(request, "portal/cadastro.html", {"form": form, "bloqueado": True})
    if request.POST.get("site"):  # robô preencheu a armadilha
        return redirect("login")
    form = CadastroForm(request.POST)
    if form.is_valid():
        try:
            usuario = _criar_cadastro(form.cleaned_data, form.dados_cnpj)
        except IntegrityError:  # outro cadastro igual entrou no mesmo instante
            form.add_error(None, "Esse e-mail ou essa empresa já tem cadastro. Fale com o escritório.")
        else:
            login(request, usuario)
            return redirect("portal:inicio")
    return render(request, "portal/cadastro.html", {"form": form})


def termos(request):
    return render(request, "portal/termos.html", {"versao": TERMOS_VERSAO})


def privacidade(request):
    return render(request, "portal/privacidade.html", {"versao": TERMOS_VERSAO})
