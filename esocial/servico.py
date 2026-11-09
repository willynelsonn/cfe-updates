"""Orquestra geração, assinatura, envio e consulta dos eventos do eSocial.

Fluxo automático
----------------
Cada evento guarda uma ``chave`` (o que ele representa) e a lista ``depende`` (chaves que
precisam estar ACEITAS antes de ele ser enviado). ``processar_fila`` consulta os lotes
já enviados e transmite apenas os eventos cujas dependências foram aceitas. Chamado
repetidamente (pela tela, a cada poucos segundos, ou pelo comando ``processar_esocial``
no agendador do servidor), ele leva tudo até o fim sem intervenção:

    S-1000 → S-1005/S-1020/S-1010 → S-2200 → S-2230/S-2299
                                           → S-1200 → S-1210 → S-1299 → DCTFWeb / FGTS Digital
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from django.db import transaction
from django.utils import timezone
from lxml import etree

from folha.models import Competencia, Ferias, Holerite, Rubrica, criar_rubricas_padrao

from . import xml_eventos as xe
from .assinatura import Certificado, ErroCertificado, assinar, carregar_pfx
from .models import Evento, Lote
from .validacao import validar_evento, validar_lote
from .webservice import MAX_EVENTOS_LOTE, ErroWebservice, consultar_lote, enviar_lote, montar_lote

ATIVOS = ("pendente", "enviado", "aceito")  # eventos que "contam" (não descartados)


class ErroESocial(Exception):
    pass


# ---------------------------------------------------------------------------
# Chaves e dependências
# ---------------------------------------------------------------------------
def chave_tabela(tipo: str, sufixo: str = "") -> str:
    return f"{tipo}:{sufixo}" if sufixo else tipo


def chave_admissao(funcionario) -> str:
    return f"S-2200:func:{funcionario.pk}"


def chave_s1010(rubrica) -> str:
    return f"S-1010:{rubrica.codigo}"


def chave_s1010_codigo(codigo: str) -> str:
    return f"S-1010:{codigo}"


def chave_s1200(competencia, funcionario) -> str:
    return f"S-1200:{competencia.per_apur}:func:{funcionario.pk}"


def _deps_empresa(empresa, *tipos) -> list[str]:
    return [] if empresa.esocial_ja_iniciado else list(tipos)


def _dep_admissao(funcionario) -> list[str]:
    return [] if funcionario.esocial_ja_cadastrado else [chave_admissao(funcionario)]


def _registrar(empresa, tipo, descricao, id_evento, root, *, chave="", depende=(), **extra) -> Evento:
    xml = xe.para_bytes(root)
    erros = validar_evento(tipo, xml, assinado=False)
    # Um novo evento com a mesma chave substitui os anteriores que ainda não foram aceitos.
    if chave:
        Evento.objects.filter(empresa=empresa, chave=chave, status__in=["pendente", "erro", "rejeitado"]).delete()
    return Evento.objects.create(
        empresa=empresa, tipo=tipo, descricao=descricao, id_evento=id_evento, xml=xml.decode(),
        status="erro" if erros else "pendente", mensagens=[f"Schema: {e}" for e in erros],
        chave=chave, depende=list(depende), **extra,
    )


def _ja_existe(empresa, chave: str) -> bool:
    return Evento.objects.filter(empresa=empresa, chave=chave, status__in=ATIVOS).exists()


# ---------------------------------------------------------------------------
# Geração
# ---------------------------------------------------------------------------
@transaction.atomic
def sincronizar_tabelas(empresa) -> list[Evento]:
    """Gera o que faltar dos eventos de tabela: S-1000, S-1005, S-1020 e S-1010 de cada rubrica ativa."""
    if not empresa.cnae or len(empresa.cnae) != 7:
        raise ErroESocial("Complete o CNAE (7 dígitos) no cadastro da empresa.")
    criar_rubricas_padrao(empresa)
    eventos = []
    if not empresa.esocial_ja_iniciado:
        for tipo, desc, fn, deps in (
            ("S-1000", "Informações do empregador", xe.s1000, []),
            ("S-1005", "Estabelecimento matriz", xe.s1005, ["S-1000"]),
            ("S-1020", f"Lotação {empresa.cod_lotacao_padrao}", xe.s1020, ["S-1000"]),
        ):
            if not _ja_existe(empresa, tipo):
                eventos.append(_registrar(empresa, tipo, desc, *fn(empresa), chave=tipo, depende=deps))
    for rub in Rubrica.objects.filter(empresa=empresa, ativa=True):
        chave = chave_s1010(rub)
        if not _ja_existe(empresa, chave):
            eventos.append(_registrar(empresa, "S-1010", f"Rubrica {rub}", *xe.s1010(empresa, rub),
                                      chave=chave, depende=_deps_empresa(empresa, "S-1000")))
    return eventos


# Compatibilidade com a versão anterior
gerar_eventos_iniciais = sincronizar_tabelas


def gerar_admissao(funcionario) -> Evento:
    if not funcionario.empresa.cnpj_sindicato:
        raise ErroESocial("Informe o CNPJ do sindicato no cadastro da empresa (obrigatório no S-2200).")
    if funcionario.esocial_ja_cadastrado:
        raise ErroESocial("Este funcionário está marcado como já cadastrado no eSocial por outro sistema.")
    empresa = funcionario.empresa
    return _registrar(
        empresa, "S-2200", f"Admissão de {funcionario.nome}", *xe.s2200(funcionario),
        chave=chave_admissao(funcionario), depende=_deps_empresa(empresa, "S-1000", "S-1005", "S-1020"),
        funcionario=funcionario,
    )


def gerar_desligamento(funcionario) -> Evento:
    from folha.models import Rescisao

    if not funcionario.data_desligamento or not funcionario.motivo_desligamento:
        raise ErroESocial("Informe a data e o motivo do desligamento no cadastro do funcionário.")
    resc = Rescisao.objects.filter(funcionario=funcionario).exclude(status="cancelada").first()
    if resc:
        sincronizar_tabelas(funcionario.empresa)  # rubricas de rescisão precisam estar no eSocial
    deps = _dep_admissao(funcionario) + (
        sorted({chave_s1010_codigo(i["codigo"]) for i in resc.itens}) if resc else []
    )
    return _registrar(
        funcionario.empresa, "S-2299", f"Desligamento de {funcionario.nome}", *xe.s2299(funcionario, resc),
        chave=f"S-2299:func:{funcionario.pk}", depende=deps, funcionario=funcionario,
    )


def gerar_ferias(ferias: Ferias) -> Evento:
    f = ferias.funcionario
    return _registrar(
        f.empresa, "S-2230", f"Férias de {f.nome} ({ferias.inicio:%d/%m} a {ferias.fim:%d/%m/%Y})",
        *xe.s2230_ferias(ferias), chave=f"S-2230:ferias:{ferias.pk}", depende=_dep_admissao(f),
        funcionario=f, ferias=ferias,
    )


@transaction.atomic
def fechar_competencia(competencia: Competencia, transmitir_dctfweb: bool = False) -> list[Evento]:
    """Gera S-1200 (um por trabalhador), S-1210 (pagamentos feitos neste mês) e S-1299.

    O S-1210 segue o regime de CAIXA: entra no mês em que o dinheiro foi pago. Por isso o
    salário de outubro pago em 05/11 é informado no S-1210 de novembro, junto com férias e
    1ª parcela do 13º pagas em novembro.
    """
    if competencia.status != "calculada":
        raise ErroESocial("Calcule a folha antes de fechar a competência.")
    empresa = competencia.empresa
    holerites = list(competencia.holerites.select_related("funcionario", "competencia"))
    if not holerites:
        raise ErroESocial("Nenhum holerite calculado nesta competência.")

    pagos_no_mes: list = []
    if not competencia.decimo_terceiro:
        pagos_no_mes = list(
            Holerite.objects.filter(
                competencia__empresa=empresa,
                data_pagamento__gte=competencia.inicio,
                data_pagamento__lte=competencia.fim,
            ).select_related("funcionario", "competencia")
        )
        abertas = {str(h.competencia) for h in pagos_no_mes
                   if h.competencia_id != competencia.pk and h.competencia.status != "fechada"}
        if abertas:
            raise ErroESocial(
                f"Há pagamentos feitos em {competencia} que pertencem a folhas ainda não fechadas "
                f"({', '.join(sorted(abertas))}). Feche essas folhas primeiro."
            )

    sincronizar_tabelas(empresa)  # garante S-1010 de rubricas novas
    eventos = []
    por_func: dict[int, list[Holerite]] = defaultdict(list)
    for h in holerites:
        por_func[h.funcionario_id].append(h)
    for hs in por_func.values():
        func = hs[0].funcionario
        rubricas = {i.rubrica for h in hs for i in h.itens.select_related("rubrica")}
        deps = _dep_admissao(func) + sorted(chave_s1010(r) for r in rubricas)
        eventos.append(_registrar(
            empresa, "S-1200", f"Remuneração {competencia} - {func.nome}", *xe.s1200(competencia, func, hs),
            chave=chave_s1200(competencia, func), depende=deps,
            funcionario=func, competencia=competencia, per_apur=competencia.per_apur,
        ))

    if not competencia.decimo_terceiro:
        from folha.models import Rescisao

        pagos_no_mes += list(Rescisao.objects.filter(
            funcionario__empresa=empresa, data_pagamento__gte=competencia.inicio,
            data_pagamento__lte=competencia.fim,
        ).exclude(status="cancelada").select_related("funcionario"))
    pg_por_cpf: dict[str, list] = defaultdict(list)
    for h in pagos_no_mes:
        pg_por_cpf[h.funcionario.cpf].append(h)
    for cpf, hs in pg_por_cpf.items():
        func = hs[0].funcionario
        deps = sorted({
            f"S-2299:func:{func.pk}" if getattr(h, "eh_rescisao", False) else chave_s1200(h.competencia, func)
            for h in hs
        })
        id_evento, root = xe.s1210(empresa, competencia.per_apur, cpf, hs)
        eventos.append(_registrar(
            empresa, "S-1210", f"Pagamentos de {competencia} - {func.nome}", id_evento, root,
            chave=f"S-1210:{competencia.per_apur}:cpf:{cpf}", depende=deps,
            funcionario=func, competencia=competencia, per_apur=competencia.per_apur,
        ))

    deps_fech = [e.chave for e in eventos]
    eventos.append(_registrar(
        empresa, "S-1299", f"Fechamento {competencia}",
        *xe.s1299(empresa, competencia.per_apur, True, bool(pg_por_cpf), transmitir_dctfweb,
                  competencia.ind_apuracao),
        chave=f"S-1299:{competencia.per_apur}", depende=deps_fech,
        competencia=competencia, per_apur=competencia.per_apur,
    ))
    competencia.status = "fechada"
    competencia.save(update_fields=["status"])
    return eventos


def regerar(evento: Evento) -> Evento:
    """Gera de novo um evento rejeitado, com os dados corrigidos do cadastro."""
    if not evento.corrigivel:
        raise ErroESocial("Só eventos com erro ou rejeitados podem ser gerados novamente.")
    if evento.tipo == "S-2200" and evento.funcionario:
        return gerar_admissao(evento.funcionario)
    if evento.tipo == "S-2299" and evento.funcionario:
        return gerar_desligamento(evento.funcionario)
    if evento.tipo == "S-2230" and evento.ferias:
        return gerar_ferias(evento.ferias)
    if evento.tipo in {"S-1000", "S-1005", "S-1020", "S-1010"}:
        evento.delete()
        sincronizar_tabelas(evento.empresa)
        return Evento.objects.filter(empresa=evento.empresa, chave=evento.chave).first()
    raise ErroESocial(
        "Eventos da folha (S-1200/S-1210/S-1299) com erro exigem corrigir o cadastro e reenviar o evento "
        "como está (botão Reenviar) ou retificar a folha com o contador."
    )


# ---------------------------------------------------------------------------
# Envio e consulta
# ---------------------------------------------------------------------------
def certificado_da_empresa(empresa) -> Certificado:
    if not empresa.tem_certificado:
        raise ErroESocial("Cadastre o certificado digital A1 (.pfx) e a senha na empresa.")
    with empresa.certificado.open("rb") as fh:
        return carregar_pfx(fh.read(), empresa.senha_certificado)


def _assinar_evento(evento: Evento, cert: Certificado) -> etree._Element:
    assinado = assinar(etree.fromstring(evento.xml.encode()), cert)
    evento.xml_assinado = etree.tostring(assinado, encoding="unicode")
    return assinado


def _dependencias_faltando(evento: Evento, aceitas: set[str]) -> list[str]:
    return [d for d in evento.depende if d not in aceitas]


def _descrever(chave: str) -> str:
    return chave.split(":")[0]


def transmitir_pendentes(empresa, cert: Certificado | None = None) -> list[Lote]:
    """Assina e envia os eventos da fila cujas dependências já foram aceitas (lotes de até 50)."""
    cert = cert or certificado_da_empresa(empresa)
    aceitas = set(Evento.objects.filter(empresa=empresa, status="aceito").values_list("chave", flat=True))
    prontos: dict[int, list[Evento]] = defaultdict(list)
    for ev in Evento.objects.filter(empresa=empresa, status="pendente").order_by("criado_em", "pk"):
        faltam = _dependencias_faltando(ev, aceitas)
        if faltam:
            msg = "Aguardando aceite de: " + ", ".join(sorted({_descrever(f) for f in faltam}))
            if ev.mensagens != [msg]:
                ev.mensagens = [msg]
                ev.save(update_fields=["mensagens"])
            continue
        prontos[ev.grupo].append(ev)
    lotes = []
    for grupo in (1, 2, 3):
        evs = prontos[grupo]
        for i in range(0, len(evs), MAX_EVENTOS_LOTE):
            lotes.append(_enviar(empresa, grupo, evs[i : i + MAX_EVENTOS_LOTE], cert))
    return lotes


def _enviar(empresa, grupo, eventos: list[Evento], cert: Certificado) -> Lote:
    assinados = [(ev.id_evento, _assinar_evento(ev, cert)) for ev in eventos]
    lote_xml = montar_lote(grupo, empresa, assinados)
    erros = validar_lote(lote_xml)
    lote = Lote.objects.create(
        empresa=empresa, grupo=grupo, ambiente=empresa.ambiente_esocial,
        xml_envio=etree.tostring(lote_xml, encoding="unicode"),
    )
    if erros:
        lote.status, lote.desc_resposta = "erro", "; ".join(erros)
        lote.save()
        return lote
    try:
        ret = enviar_lote(empresa.ambiente_esocial, lote_xml, cert)
    except ErroWebservice as exc:
        lote.status, lote.desc_resposta = "erro", str(exc)
        lote.save()
        return lote  # eventos continuam na fila e serão tentados de novo
    lote.xml_retorno_envio = ret.xml.decode(errors="replace")
    lote.cd_resposta, lote.desc_resposta, lote.protocolo = ret.cd_resposta, ret.desc_resposta, ret.protocolo
    lote.status = "enviado" if ret.aceito else "rejeitado"
    lote.save()
    for ev in eventos:
        ev.lote = lote
        if ret.aceito:
            ev.status, ev.mensagens = "enviado", []
        else:
            ev.status = "rejeitado"
            ev.mensagens = [f"Lote recusado: {ret.cd_resposta} {ret.desc_resposta}", *ret.ocorrencias]
        ev.save()
    return lote


def consultar_lotes_enviados(empresa, cert: Certificado | None = None) -> list[Lote]:
    cert = cert or certificado_da_empresa(empresa)
    atualizados = []
    for lote in Lote.objects.filter(empresa=empresa, status="enviado").exclude(protocolo=""):
        try:
            ret = consultar_lote(lote.ambiente, lote.protocolo, cert)
        except ErroWebservice as exc:
            lote.desc_resposta = str(exc)
            lote.save(update_fields=["desc_resposta"])
            continue
        lote.xml_retorno_consulta = ret.xml.decode(errors="replace")
        lote.consultado_em = timezone.now()
        lote.cd_resposta, lote.desc_resposta = ret.cd_resposta, ret.desc_resposta
        if not ret.em_processamento:
            lote.status = "processado"
            por_id = {r.id_evento: r for r in ret.eventos}
            for ev in lote.eventos.all():
                r = por_id.get(ev.id_evento)
                if r is None:
                    continue
                ev.status = "aceito" if r.sucesso else "rejeitado"
                ev.recibo = r.recibo
                ev.mensagens = [f"{r.cd_resposta} {r.desc_resposta}", *r.ocorrencias]
                ev.save()
        lote.save()
        atualizados.append(lote)
    return atualizados


def processar_fila(empresa) -> dict:
    """Um "passo" da automação: consulta o que foi enviado e envia o que ficou liberado."""
    cert = certificado_da_empresa(empresa)
    if not Evento.objects.filter(empresa=empresa, chave="S-1000").exists() and not empresa.esocial_ja_iniciado:
        sincronizar_tabelas(empresa)  # primeiro uso: cadastra a empresa e as rubricas sozinho
    consultados = consultar_lotes_enviados(empresa, cert)
    enviados = transmitir_pendentes(empresa, cert)
    return {"consultados": len(consultados), "lotes_enviados": len(enviados), **situacao_fila(empresa)}


def situacao_fila(empresa) -> dict:
    qs = Evento.objects.filter(empresa=empresa)
    return {
        "pendentes": qs.filter(status="pendente").count(),
        "enviados": qs.filter(status="enviado").count(),
        "aceitos": qs.filter(status="aceito").count(),
        "problemas": qs.filter(status__in=["erro", "rejeitado"]).count(),
        "lotes_aguardando": Lote.objects.filter(empresa=empresa, status="enviado").count(),
    }


def tentar_processar(empresa) -> str | None:
    """Usado pelos gatilhos automáticos: nunca levanta exceção, devolve a mensagem de problema."""
    if not empresa.envio_automatico:
        return None
    try:
        processar_fila(empresa)
    except (ErroESocial, ErroCertificado) as exc:
        return f"Envio automático ao eSocial pausado: {exc}"
    return None


def reenviar(evento: Evento) -> Evento:
    """Volta um evento com erro de comunicação para a fila, sem alterar o XML."""
    if evento.corrigivel:
        evento.status = "pendente"
        evento.lote = None
        evento.save()
    return evento


def data_pagamento_padrao(ano: int, mes: int, dia: int = 5) -> date:
    """Dia ``dia`` do mês seguinte, limitado ao 5º dia útil (CLT art. 459, §1º)."""
    from folha.calculo import quinto_dia_util

    proximo_ano, proximo_mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return min(date(proximo_ano, proximo_mes, min(dia, 28)), quinto_dia_util(proximo_ano, proximo_mes))
