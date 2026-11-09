"""Geração dos XMLs dos eventos do eSocial (leiaute S-1.3).

Cada função recebe objetos do sistema e devolve ``(id_evento, elemento lxml)``
ainda sem assinatura. A assinatura é feita em ``assinatura.py`` e a validação
contra os XSDs oficiais em ``validacao.py``.
"""

from __future__ import annotations

import itertools
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from lxml import etree

NS_EVENTO = "http://www.esocial.gov.br/schema/evt/{nome}/{versao}"

# tipo -> (elemento raiz, grupo do lote)
EVENTOS = {
    "S-1000": ("evtInfoEmpregador", 1),
    "S-1005": ("evtTabEstab", 1),
    "S-1010": ("evtTabRubrica", 1),
    "S-1020": ("evtTabLotacao", 1),
    "S-2200": ("evtAdmissao", 2),
    "S-2230": ("evtAfastTemp", 2),
    "S-2299": ("evtDeslig", 2),
    "S-1200": ("evtRemun", 3),
    "S-1210": ("evtPgtos", 3),
    "S-1299": ("evtFechaEvPer", 3),
}

_sequencia = itertools.count(1)


def gerar_id(empresa, momento: datetime | None = None) -> str:
    """ID + tpInsc + nrInsc (14, completado com zeros à direita) + AAAAMMDDHHMMSS + sequencial (5)."""
    momento = timezone.localtime(momento or timezone.now())
    nr = empresa.nr_insc_esocial.ljust(14, "0")
    seq = next(_sequencia) % 100000 or 1
    return f"ID{empresa.tp_insc}{nr}{momento:%Y%m%d%H%M%S}{seq:05d}"


def _fmt(valor) -> str:
    if isinstance(valor, Decimal):
        return f"{valor:.2f}"
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%Y-%m-%d")
    return str(valor)


def sub(parent, tag, texto=None):
    """Cria subelemento no mesmo namespace do pai; ignora valores vazios."""
    ns = etree.QName(parent).namespace
    el = etree.SubElement(parent, f"{{{ns}}}{tag}")
    if texto is not None:
        el.text = _fmt(texto)
    return el


def opt(parent, tag, texto):
    if texto not in (None, ""):
        return sub(parent, tag, texto)
    return None


def _raiz(tipo: str, empresa):
    nome, _ = EVENTOS[tipo]
    ns = NS_EVENTO.format(nome=nome, versao=settings.ESOCIAL_VERSAO_LAYOUT)
    root = etree.Element(f"{{{ns}}}eSocial", nsmap={None: ns})
    evt = etree.SubElement(root, f"{{{ns}}}{nome}")
    id_evento = gerar_id(empresa)
    evt.set("Id", id_evento)
    return id_evento, root, evt


def _ide_evento(evt, empresa, *, retif=None, apuracao=None, per_apur=None, tabela=False):
    ide = sub(evt, "ideEvento")
    if retif is not None:
        sub(ide, "indRetif", 1)
    if apuracao is not None:
        sub(ide, "indApuracao", apuracao)
    if per_apur is not None:
        sub(ide, "perApur", per_apur)
    sub(ide, "tpAmb", empresa.ambiente_esocial)
    sub(ide, "procEmi", 1)  # aplicativo do empregador
    sub(ide, "verProc", settings.ESOCIAL_VER_PROC)
    return ide


def _ide_empregador(evt, empresa):
    ide = sub(evt, "ideEmpregador")
    sub(ide, "tpInsc", empresa.tp_insc)
    sub(ide, "nrInsc", empresa.nr_insc_esocial)
    return ide


def _ide_estab_lot(parent, empresa, tag="ideEstabLot"):
    el = sub(parent, tag)
    sub(el, "tpInsc", empresa.tp_insc if empresa.tp_insc == 1 else 3)
    sub(el, "nrInsc", empresa.nr_insc)
    sub(el, "codLotacao", empresa.cod_lotacao_padrao)
    return el


# ---------------------------------------------------------------------------
# Eventos de tabela
# ---------------------------------------------------------------------------
def s1000(empresa):
    """Informações do empregador."""
    id_evento, root, evt = _raiz("S-1000", empresa)
    _ide_evento(evt, empresa)
    _ide_empregador(evt, empresa)
    info = sub(evt, "infoEmpregador")
    inc = sub(info, "inclusao")
    per = sub(inc, "idePeriodo")
    sub(per, "iniValid", empresa.inicio_esocial)
    cad = sub(inc, "infoCadastro")
    sub(cad, "classTrib", empresa.class_trib)
    sub(cad, "indCoop", 0)
    sub(cad, "indConstr", 0)
    sub(cad, "indDesFolha", 0)
    sub(cad, "indOptRegEletron", 0)
    return id_evento, root


def s1005(empresa):
    """Tabela de estabelecimentos (matriz)."""
    id_evento, root, evt = _raiz("S-1005", empresa)
    _ide_evento(evt, empresa)
    _ide_empregador(evt, empresa)
    info = sub(evt, "infoEstab")
    inc = sub(info, "inclusao")
    ide = sub(inc, "ideEstab")
    sub(ide, "tpInsc", 1 if empresa.tp_insc == 1 else 3)
    sub(ide, "nrInsc", empresa.nr_insc)
    sub(ide, "iniValid", empresa.inicio_esocial)
    dados = sub(inc, "dadosEstab")
    sub(dados, "cnaePrep", empresa.cnae)
    if empresa.recolhe_cpp_patronal:
        gil = sub(dados, "aliqGilrat")
        sub(gil, "aliqRat", empresa.aliq_rat)
        sub(gil, "fap", f"{empresa.fap:.4f}")
    return id_evento, root


def s1010(empresa, rubrica):
    """Tabela de rubricas."""
    id_evento, root, evt = _raiz("S-1010", empresa)
    _ide_evento(evt, empresa)
    _ide_empregador(evt, empresa)
    info = sub(evt, "infoRubrica")
    inc = sub(info, "inclusao")
    ide = sub(inc, "ideRubrica")
    sub(ide, "codRubr", rubrica.codigo)
    sub(ide, "ideTabRubr", rubrica.ide_tab_rubr)
    sub(ide, "iniValid", empresa.inicio_esocial)
    dados = sub(inc, "dadosRubrica")
    sub(dados, "dscRubr", rubrica.descricao)
    sub(dados, "natRubr", rubrica.natureza)
    sub(dados, "tpRubr", rubrica.tipo)
    sub(dados, "codIncCP", rubrica.inc_cp)
    sub(dados, "codIncIRRF", rubrica.inc_irrf)
    sub(dados, "codIncFGTS", rubrica.inc_fgts)
    return id_evento, root


def s1020(empresa):
    """Tabela de lotações tributárias (lotação única padrão)."""
    id_evento, root, evt = _raiz("S-1020", empresa)
    _ide_evento(evt, empresa)
    _ide_empregador(evt, empresa)
    info = sub(evt, "infoLotacao")
    inc = sub(info, "inclusao")
    ide = sub(inc, "ideLotacao")
    sub(ide, "codLotacao", empresa.cod_lotacao_padrao)
    sub(ide, "iniValid", empresa.inicio_esocial)
    dados = sub(inc, "dadosLotacao")
    sub(dados, "tpLotacao", "01")  # classificação da atividade econômica exercida pela PJ
    fpas = sub(dados, "fpasLotacao")
    sub(fpas, "fpas", empresa.fpas)
    sub(fpas, "codTercs", empresa.cod_terceiros)
    return id_evento, root


# ---------------------------------------------------------------------------
# Eventos não periódicos
# ---------------------------------------------------------------------------
def s2200(funcionario):
    """Cadastramento inicial do vínculo e admissão do trabalhador."""
    empresa = funcionario.empresa
    f = funcionario
    id_evento, root, evt = _raiz("S-2200", empresa)
    _ide_evento(evt, empresa, retif=1)
    _ide_empregador(evt, empresa)

    trab = sub(evt, "trabalhador")
    sub(trab, "cpfTrab", f.cpf)
    sub(trab, "nmTrab", f.nome)
    sub(trab, "sexo", f.sexo)
    sub(trab, "racaCor", f.raca_cor)
    opt(trab, "estCiv", f.estado_civil)
    sub(trab, "grauInstr", f.grau_instrucao)
    opt(trab, "nmSoc", f.nome_social)
    nasc = sub(trab, "nascimento")
    sub(nasc, "dtNascto", f.data_nascimento)
    sub(nasc, "paisNascto", "105")
    sub(nasc, "paisNac", "105")
    end = sub(trab, "endereco")
    br = sub(end, "brasil")
    sub(br, "dscLograd", f.logradouro)
    sub(br, "nrLograd", f.numero or "S/N")
    opt(br, "complemento", f.complemento)
    opt(br, "bairro", f.bairro)
    sub(br, "cep", f.cep)
    sub(br, "codMunic", f.cod_municipio)
    sub(br, "uf", f.uf)
    for d in f.dependentes.all():
        dep = sub(trab, "dependente")
        sub(dep, "tpDep", d.tipo)
        sub(dep, "nmDep", d.nome)
        sub(dep, "dtNascto", d.data_nascimento)
        opt(dep, "cpfDep", d.cpf)
        opt(dep, "sexoDep", d.sexo)
        sub(dep, "depIRRF", "S" if d.dependente_irrf else "N")
        sub(dep, "depSF", "S" if d.dependente_salario_familia else "N")
        sub(dep, "incTrab", "S" if d.incapaz else "N")
    if f.telefone or f.email:
        cont = sub(trab, "contato")
        if f.telefone and len(f.telefone) >= 8:
            sub(cont, "fonePrinc", f.telefone)
        opt(cont, "emailPrinc", f.email)

    vinc = sub(evt, "vinculo")
    sub(vinc, "matricula", f.matricula)
    sub(vinc, "tpRegTrab", 1)  # CLT
    sub(vinc, "tpRegPrev", 1)  # RGPS
    sub(vinc, "cadIni", "N")
    regime = sub(vinc, "infoRegimeTrab")
    clt = sub(regime, "infoCeletista")
    sub(clt, "dtAdm", f.data_admissao)
    sub(clt, "tpAdmissao", 1)  # admissão
    sub(clt, "indAdmissao", 1)  # normal
    sub(clt, "tpRegJor", 1)  # submetido a horário de trabalho
    sub(clt, "natAtividade", 1)  # urbano
    sub(clt, "cnpjSindCategProf", empresa.cnpj_sindicato or "")
    fgts = sub(clt, "FGTS")
    sub(fgts, "dtOpcFGTS", f.data_admissao)

    contrato = sub(vinc, "infoContrato")
    sub(contrato, "nmCargo", f.cargo.nome)
    sub(contrato, "CBOCargo", f.cargo.cbo)
    sub(contrato, "codCateg", f.categoria)
    rem = sub(contrato, "remuneracao")
    sub(rem, "vrSalFx", f.salario)
    sub(rem, "undSalFixo", 5)  # por mês
    dur = sub(contrato, "duracao")
    sub(dur, "tpContr", f.tipo_contrato)
    if f.tipo_contrato == 2 and f.data_termino:
        sub(dur, "dtTerm", f.data_termino)
    local = sub(contrato, "localTrabalho")
    geral = sub(local, "localTrabGeral")
    sub(geral, "tpInsc", 1 if empresa.tp_insc == 1 else 3)
    sub(geral, "nrInsc", empresa.nr_insc)
    hor = sub(contrato, "horContratual")
    sub(hor, "qtdHrsSem", f"{f.horas_semanais:.2f}")
    sub(hor, "tpJornada", f.tipo_jornada)
    sub(hor, "tmpParc", 0 if f.horas_semanais > 30 else 1)
    sub(hor, "dscJorn", f.descricao_jornada)
    return id_evento, root


def s2299(funcionario, rescisao=None):
    """Desligamento, com as verbas rescisórias (verbasResc) quando a rescisão foi calculada."""
    empresa = funcionario.empresa
    f = funcionario
    id_evento, root, evt = _raiz("S-2299", empresa)
    _ide_evento(evt, empresa, retif=1)
    _ide_empregador(evt, empresa)
    vinc = sub(evt, "ideVinculo")
    sub(vinc, "cpfTrab", f.cpf)
    sub(vinc, "matricula", f.matricula)
    info = sub(evt, "infoDeslig")
    sub(info, "mtvDeslig", f.motivo_desligamento)
    sub(info, "dtDeslig", f.data_desligamento)
    sub(info, "indPagtoAPI", "S" if f.aviso_previo_indenizado else "N")
    if f.aviso_previo_indenizado:
        from folha.calculo import aviso_previo_dias
        from datetime import timedelta

        if rescisao is not None and rescisao.data_projetada:
            sub(info, "dtProjFimAPI", rescisao.data_projetada)
        else:
            dias = aviso_previo_dias(f.data_admissao, f.data_desligamento)
            sub(info, "dtProjFimAPI", f.data_desligamento + timedelta(days=dias))
    sub(info, "pensAlim", 0)
    if rescisao is not None:
        from folha.models import Rubrica

        codigos = {r.codigo: r for r in Rubrica.objects.filter(empresa=empresa)}
        verbas = sub(info, "verbasResc")
        dm = sub(verbas, "dmDev")
        sub(dm, "ideDmDev", rescisao.ide_dm_dev)
        per = sub(dm, "infoPerApur")
        estab = _ide_estab_lot(per, empresa)
        for item in rescisao.itens:
            det = sub(estab, "detVerbas")
            rub = codigos[item["codigo"]]
            sub(det, "codRubr", rub.codigo)
            sub(det, "ideTabRubr", rub.ide_tab_rubr)
            if item["referencia"]:
                sub(det, "qtdRubr", Decimal(item["referencia"]))
            sub(det, "vrRubr", Decimal(item["valor"]))
            sub(det, "indApurIR", 0)
        nocivo = sub(estab, "infoAgNocivo")
        sub(nocivo, "grauExp", 1)
    return id_evento, root


# ---------------------------------------------------------------------------
# Eventos periódicos
# ---------------------------------------------------------------------------
def s1200(competencia, funcionario, holerites):
    """Remuneração do trabalhador: um evento por trabalhador e período, com um dmDev por demonstrativo
    (folha mensal, recibo de férias, 1ª parcela do 13º) ou o 13º anual (indApuracao = 2)."""
    empresa = competencia.empresa
    f = funcionario
    id_evento, root, evt = _raiz("S-1200", empresa)
    _ide_evento(evt, empresa, retif=1, apuracao=competencia.ind_apuracao, per_apur=competencia.per_apur)
    _ide_empregador(evt, empresa)
    trab = sub(evt, "ideTrabalhador")
    sub(trab, "cpfTrab", f.cpf)
    for holerite in holerites:
        itens = list(holerite.itens.select_related("rubrica"))
        if not itens:
            continue
        dm = sub(evt, "dmDev")
        sub(dm, "ideDmDev", holerite.ide_dm_dev)
        sub(dm, "codCateg", f.categoria)
        per = sub(dm, "infoPerApur")
        estab = _ide_estab_lot(per, empresa)
        rem = sub(estab, "remunPerApur")
        sub(rem, "matricula", f.matricula)
        for item in itens:
            it = sub(rem, "itensRemun")
            sub(it, "codRubr", item.rubrica.codigo)
            sub(it, "ideTabRubr", item.rubrica.ide_tab_rubr)
            if item.referencia is not None:
                sub(it, "qtdRubr", item.referencia)
            sub(it, "vrRubr", item.valor)
            sub(it, "indApurIR", 0)
        nocivo = sub(rem, "infoAgNocivo")
        sub(nocivo, "grauExp", 1)  # não exposto a agente nocivo
    return id_evento, root


def s1210(empresa, per_apur: str, cpf: str, holerites):
    """Pagamentos feitos no mês ``per_apur`` (regime de caixa) a um beneficiário."""
    id_evento, root, evt = _raiz("S-1210", empresa)
    _ide_evento(evt, empresa, retif=1, per_apur=per_apur)
    _ide_empregador(evt, empresa)
    benef = sub(evt, "ideBenef")
    sub(benef, "cpfBenef", cpf)
    for h in holerites:
        pg = sub(benef, "infoPgto")
        sub(pg, "dtPgto", h.data_pagamento)
        rescisao = getattr(h, "eh_rescisao", False)
        sub(pg, "tpPgto", 2 if rescisao else 1)  # 2 = verbas rescisórias do S-2299; 1 = S-1200
        sub(pg, "perRef", h.per_apur if rescisao else h.competencia.per_apur)
        sub(pg, "ideDmDev", h.ide_dm_dev)
        sub(pg, "vrLiq", max(h.liquido, Decimal("0")))
    return id_evento, root


def s1299(empresa, per_apur: str, tem_remun: bool, tem_pgtos: bool, transmitir_dctfweb: bool = False,
          ind_apuracao: int = 1):
    """Fechamento dos eventos periódicos — gera a DCTFWeb e alimenta o FGTS Digital.

    Com ``transmitir_dctfweb`` a Receita transmite a DCTFWeb automaticamente após o
    fechamento (campo transDCTFWeb); sem ele a DCTFWeb fica "em andamento" no e-CAC.
    """
    id_evento, root, evt = _raiz("S-1299", empresa)
    _ide_evento(evt, empresa, apuracao=ind_apuracao, per_apur=per_apur)
    _ide_empregador(evt, empresa)
    info = sub(evt, "infoFech")
    sub(info, "evtRemun", "S" if tem_remun else "N")
    sub(info, "evtPgtos", "S" if tem_pgtos else "N")
    sub(info, "evtComProd", "N")
    sub(info, "evtContratAvNP", "N")
    sub(info, "evtInfoComplPer", "N")
    if transmitir_dctfweb or empresa.class_trib == "04":
        sub(info, "transDCTFWeb", "S")
    return id_evento, root


def s2230_ferias(ferias):
    """Afastamento por férias (motivo 15), com início e término no mesmo evento."""
    f = ferias.funcionario
    empresa = f.empresa
    id_evento, root, evt = _raiz("S-2230", empresa)
    _ide_evento(evt, empresa, retif=1)
    _ide_empregador(evt, empresa)
    vinc = sub(evt, "ideVinculo")
    sub(vinc, "cpfTrab", f.cpf)
    sub(vinc, "matricula", f.matricula)
    info = sub(evt, "infoAfastamento")
    ini = sub(info, "iniAfastamento")
    sub(ini, "dtIniAfast", ferias.inicio)
    sub(ini, "codMotAfast", "15")
    per = sub(ini, "perAquis")
    sub(per, "dtInicio", ferias.aquisitivo_inicio)
    sub(per, "dtFim", ferias.aquisitivo_fim)
    fim = sub(info, "fimAfastamento")
    sub(fim, "dtTermAfast", ferias.fim)
    return id_evento, root


def para_bytes(root) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")
