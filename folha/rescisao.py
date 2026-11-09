"""Cálculo da rescisão do contrato de trabalho (TRCT).

Base legal principal: CLT arts. 146, 147, 477, 479, 480, 484, 484-A e 487; Lei 12.506/2011
(aviso proporcional); Lei 4.090/1962 (13º); Lei 8.036/1990, art. 18 (multa do FGTS);
Súmulas TST 14 (culpa recíproca), 171 (justa causa) e 261 (pedido de demissão);
OJ 82 SDI-1 (projeção do aviso indenizado); Súmula 386 STJ (férias indenizadas sem IR).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from . import calculo as c
from .conformidade import _somar_meses, periodos_aquisitivos
from .models import Holerite, ItemHolerite, Rescisao
from .servico import media_variaveis, remuneracao_fixa, rubricas_por_papel
from .tabelas import tabelas_do_ano

UM, MEIO = Decimal("1"), Decimal("0.5")


@dataclass(frozen=True)
class Regra:
    descricao: str
    aviso: str  # "proporcional" (Lei 12.506), "30" (pedido de demissão) ou "" (sem aviso)
    fator_aviso: Decimal = UM
    decimo: Decimal = UM  # fração do 13º proporcional
    ferias_prop: Decimal = UM  # fração das férias proporcionais
    multa_fgts: Decimal = Decimal("0")  # % sobre o saldo do FGTS
    art479: bool = False
    art480: bool = False
    saque_fgts: str = "Não"


REGRAS = {
    "01": Regra("Justa causa", "", decimo=Decimal("0"), ferias_prop=Decimal("0"),
                saque_fgts="Não (Súmula 171 TST: perde 13º e férias proporcionais)"),
    "02": Regra("Dispensa sem justa causa", "proporcional", multa_fgts=Decimal("40"), saque_fgts="Sim, 100%"),
    "03": Regra("Rescisão antecipada do contrato a termo pela empresa", "", multa_fgts=Decimal("40"), art479=True,
                saque_fgts="Sim, 100%"),
    "04": Regra("Rescisão antecipada do contrato a termo pelo empregado", "", art480=True),
    "05": Regra("Culpa recíproca", "proporcional", fator_aviso=MEIO, decimo=MEIO, ferias_prop=MEIO,
                multa_fgts=Decimal("20"), saque_fgts="Sim, 100%"),
    "06": Regra("Término do contrato a termo", "", saque_fgts="Sim, 100%"),
    "07": Regra("Pedido de demissão", "30"),
    "08": Regra("Rescisão por interesse do empregado (art. 394-A)", "30"),
    "10": Regra("Falecimento do empregado", "", saque_fgts="Sim, pelos dependentes"),
    "33": Regra("Acordo entre as partes (art. 484-A)", "proporcional", fator_aviso=MEIO,
                multa_fgts=Decimal("20"), saque_fgts="Sim, até 80% (sem seguro-desemprego)"),
}


class ErroRescisao(Exception):
    pass


def _meses_proporcionais(inicio: date, fim: date) -> int:
    """Meses de serviço no período, contando fração de 15 dias ou mais como mês (CLT art. 146, parágrafo único)."""
    meses = 0
    atual = inicio
    while True:
        prox = _somar_meses(atual, 1)
        if prox - timedelta(days=1) <= fim:
            meses += 1
            atual = prox
            continue
        if (fim - atual).days + 1 >= 15:
            meses += 1
        return min(meses, 12)


def _avos_13(admissao: date, desligamento: date, ano: int) -> int:
    if desligamento < date(ano, 1, 1):
        return 0
    return c.avos_13(ano, admissao, min(desligamento, date(ano, 12, 31)))


def calcular_rescisao(resc: Rescisao) -> Rescisao:
    f = resc.funcionario
    regra = REGRAS.get(resc.motivo)
    if regra is None:
        raise ErroRescisao("Motivo de desligamento não suportado no cálculo automático.")
    deslig = resc.data_desligamento
    if deslig < f.data_admissao:
        raise ErroRescisao("O desligamento não pode ser antes da admissão.")
    tab = tabelas_do_ano(deslig.year)
    rub = rubricas_por_papel(f.empresa)
    fixa = remuneracao_fixa(f, tab)
    media = media_variaveis(f, deslig - timedelta(days=365), deslig)
    rem = fixa + media
    diaria = rem / 30
    itens: list[tuple[str, object, Decimal]] = []
    memoria: dict = {"remuneracao": str(rem), "media_variaveis": str(media), "regra": regra.descricao}

    def add(papel, referencia, valor):
        valor = c.r2(valor)
        if valor > 0:
            itens.append((papel, referencia, valor))
        return valor

    # Aviso prévio
    dias_aviso = 0
    if regra.aviso == "proporcional":
        dias_aviso = c.aviso_previo_dias(f.data_admissao, deslig)
    elif regra.aviso == "30":
        dias_aviso = 30
    tipo = resc.tipo_aviso if dias_aviso else "nenhum"
    if regra.aviso == "30" and tipo == "indenizado":
        tipo = "dispensado"  # no pedido de demissão quem dá o aviso é o empregado
    projetada = deslig
    if tipo == "indenizado":
        dias_ind = Decimal(dias_aviso) * regra.fator_aviso  # pode ser fracionado (ex.: 16,5 no acordo)
        projetada = deslig + timedelta(days=int(dias_ind.to_integral_value(rounding="ROUND_CEILING")))
        add("resc_aviso", dias_ind, diaria * dias_ind)
    resc.dias_aviso = dias_aviso
    resc.tipo_aviso = tipo
    resc.data_projetada = projetada

    # Saldo de salário (dias do último mês)
    dias_saldo = c.dias_trabalhados(deslig.year, deslig.month, f.data_admissao, deslig)
    add("resc_saldo", dias_saldo, fixa / 30 * dias_saldo)

    # 13º proporcional (com projeção do aviso indenizado — OJ 82 SDI-1)
    ja_pago_13 = Holerite.objects.filter(funcionario=f, tipo="dec13", competencia__ano=deslig.year,
                                         competencia__status="fechada").exists()
    avos_real = 0 if ja_pago_13 else _avos_13(f.data_admissao, deslig, deslig.year)
    avos_proj = (0 if ja_pago_13 else _avos_13(f.data_admissao, projetada, deslig.year)) - avos_real
    if projetada.year > deslig.year:
        avos_proj += _avos_13(f.data_admissao, projetada, projetada.year)
    if regra.decimo:
        add("resc_13", avos_real, rem * avos_real / 12 * regra.decimo)
        add("resc_13_aviso", avos_proj, rem * avos_proj / 12 * regra.decimo)
    adiantado = ItemHolerite.objects.filter(
        holerite__funcionario=f, holerite__tipo="adiant13", holerite__competencia__ano=deslig.year
    ).values_list("valor", flat=True)
    adiantado_13 = sum(adiantado, c.ZERO) if not ja_pago_13 else c.ZERO
    memoria["avos_13"] = {"ate_desligamento": avos_real, "projecao_aviso": avos_proj}

    # Férias vencidas (períodos completos sem férias) — sempre devidas, inclusive na justa causa
    tiradas = set(f.ferias.exclude(status="cancelada").values_list("aquisitivo_inicio", flat=True))
    periodos = periodos_aquisitivos(f.data_admissao, projetada)
    vencidas = []
    for ini, fim in periodos:
        if ini in tiradas:
            continue
        dobro = _somar_meses(fim, 12) < deslig  # concessivo vencido: em dobro (CLT art. 137)
        valor = rem * (2 if dobro else 1) * Decimal(4) / 3
        vencidas.append({"inicio": str(ini), "fim": str(fim), "dobro": dobro, "valor": str(c.r2(valor))})
        add("resc_ferias_venc", 30, valor)
    memoria["ferias_vencidas"] = vencidas

    # Férias proporcionais do período em curso
    inicio_atual = periodos[-1][1] + timedelta(days=1) if periodos else f.data_admissao
    meses = _meses_proporcionais(inicio_atual, projetada) if projetada >= inicio_atual else 0
    if meses == 12:
        meses = 0  # período completo já entrou como vencido
    direito = c.dias_direito_ferias(resc.faltas_periodo_ferias)
    if regra.ferias_prop and meses:
        valor = rem * Decimal(direito) / 30 * meses / 12 * Decimal(4) / 3 * regra.ferias_prop
        add("resc_ferias_prop", meses, valor)
    memoria["ferias_proporcionais"] = {"inicio_periodo": str(inicio_atual), "meses": meses, "dias_direito": direito}

    # Contrato a termo: arts. 479 e 480
    if (regra.art479 or regra.art480) and f.data_termino and f.data_termino > deslig:
        restantes = (f.data_termino - deslig).days
        indenizacao = diaria * restantes / 2
        if regra.art479:
            add("resc_479", restantes, indenizacao)
        memoria["art_479_480"] = {"dias_restantes": restantes, "valor": str(c.r2(indenizacao))}

    proventos = sum((v for _, _, v in itens), c.ZERO)

    # Descontos
    descontos: list[tuple[str, object, Decimal]] = []
    base_mensal = sum((v for p, _, v in itens if rub[p].inc_cp == "11"), c.ZERO)
    base_13 = sum((v for p, _, v in itens if rub[p].inc_cp == "12"), c.ZERO)
    inss = c.calcular_inss(base_mensal, tab)
    inss13 = c.calcular_inss(base_13, tab) if base_13 else None
    deps = f.dependentes.filter(dependente_irrf=True).count()
    rend_mensal = sum((v for p, _, v in itens if rub[p].inc_irrf == "11"), c.ZERO)
    irrf = c.calcular_irrf(rend_mensal, inss.valor, deps, tab)
    irrf13 = c.irrf_13(base_13, inss13.valor, deps, tab) if inss13 else None
    descontos.append(("inss", inss.aliquota_efetiva, inss.valor))
    if inss13:
        descontos.append(("inss13", inss13.aliquota_efetiva, inss13.valor))
    descontos.append(("irrf", irrf.aliquota, irrf.valor))
    if irrf13:
        descontos.append(("irrf13", irrf13.aliquota, irrf13.valor))
    descontos.append(("desc_adiant13", None, adiantado_13))
    desc_aviso = c.ZERO
    if tipo == "nao_cumprido":
        desc_aviso = f.salario  # CLT art. 487, §2º: salário do prazo de 30 dias
    elif regra.art480 and "art_479_480" in memoria:
        desc_aviso = Decimal(memoria["art_479_480"]["valor"])  # limitado ao que seria devido (art. 480, §1º)
    subtotal = proventos - sum((v for _, _, v in descontos), c.ZERO)
    descontos.append(("resc_desc_aviso", None, min(desc_aviso, max(subtotal, c.ZERO))))
    descontos = [d for d in descontos if d[2] > 0]
    total_desc = sum((v for _, _, v in descontos), c.ZERO)

    # FGTS rescisório e multa (recolhidos na guia do FGTS Digital, não no TRCT)
    base_fgts = sum((v for p, _, v in itens if rub[p].inc_fgts in {"11", "12", "21"}), c.ZERO)
    fgts_mes = c.fgts(base_fgts, tab, f.aprendiz)
    multa = c.r2((resc.saldo_fgts + fgts_mes) * regra.multa_fgts / 100)

    def serial(lista, tipo_item):
        return [
            {"papel": p, "codigo": rub[p].codigo, "descricao": rub[p].descricao,
             "referencia": str(r) if r is not None else "", "valor": str(v), "tipo": tipo_item}
            for p, r, v in lista
        ]

    resc.itens = serial(itens, "provento") + serial(descontos, "desconto")
    resc.total_proventos = proventos
    resc.total_descontos = total_desc
    resc.liquido = proventos - total_desc
    resc.valor_inss = inss.valor + (inss13.valor if inss13 else 0)
    resc.valor_irrf = irrf.valor + (irrf13.valor if irrf13 else 0)
    resc.fgts_rescisorio = fgts_mes
    resc.multa_fgts = multa
    memoria.update({
        "multa_pct": str(regra.multa_fgts), "saque_fgts": regra.saque_fgts, "base_fgts": str(c.r2(base_fgts)),
        "dias_saldo": dias_saldo,
    })
    resc.memoria = memoria
    resc.status = "calculada"
    resc.save()

    # Atualiza o cadastro do funcionário (usado no S-2299)
    f.data_desligamento = deslig
    f.motivo_desligamento = resc.motivo
    f.aviso_previo_indenizado = tipo == "indenizado"
    f.save(update_fields=["data_desligamento", "motivo_desligamento", "aviso_previo_indenizado", "atualizado_em"])
    return resc


def problemas_rescisao(resc: Rescisao) -> list[tuple[str, str, str]]:
    """(título, detalhe, base legal) de irregularidades na rescisão."""
    saida = []
    if resc.data_pagamento > resc.prazo_pagamento:
        saida.append(("Pagamento fora do prazo",
                      f"O prazo é {resc.prazo_pagamento:%d/%m/%Y}. O atraso gera multa de um salário ao empregado.",
                      "CLT art. 477, §§6º e 8º"))
    if resc.motivo in {"07", "08"} and resc.tipo_aviso == "indenizado":
        saida.append(("Aviso indenizado em pedido de demissão",
                      "No pedido de demissão quem cumpre o aviso é o empregado.", "CLT art. 487"))
    return saida
