"""Verificação de conformidade trabalhista e previdenciária.

Cada regra devolve alertas com a base legal e o que fazer, para que o usuário
corrija antes que vire multa ou passivo trabalhista.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from pessoal.models import Funcionario

from . import calculo as c
from .models import Competencia, Ferias, Guia
from .tabelas import tabela_atualizada, tabelas_do_ano

CRITICO, ATENCAO, INFO = "critico", "atencao", "info"


@dataclass
class Alerta:
    nivel: str
    titulo: str
    detalhe: str
    base_legal: str
    acao_url: str = ""
    acao_texto: str = ""

    @property
    def ordem(self):
        return {CRITICO: 0, ATENCAO: 1, INFO: 2}[self.nivel]


def _somar_meses(d: date, meses: int) -> date:
    ano, mes = divmod(d.month - 1 + meses, 12)
    ano += d.year
    mes += 1
    import calendar

    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def periodos_aquisitivos(admissao: date, ate: date) -> list[tuple[date, date]]:
    """Períodos aquisitivos completos até ``ate`` (CLT art. 130)."""
    periodos = []
    inicio = admissao
    while True:
        fim = _somar_meses(inicio, 12) - timedelta(days=1)
        if fim > ate:
            return periodos
        periodos.append((inicio, fim))
        inicio = fim + timedelta(days=1)


def proximo_periodo_aquisitivo(funcionario: Funcionario, hoje: date) -> tuple[date, date]:
    """Período aquisitivo mais antigo ainda sem férias cadastradas (para sugerir na programação)."""
    usados = set(funcionario.ferias.exclude(status="cancelada").values_list("aquisitivo_inicio", flat=True))
    for ini, fim in periodos_aquisitivos(funcionario.data_admissao, hoje + timedelta(days=366)):
        if ini not in usados:
            return ini, fim
    ini = funcionario.data_admissao
    return ini, _somar_meses(ini, 12) - timedelta(days=1)


def _idade(nasc: date, em: date) -> int:
    return em.year - nasc.year - ((em.month, em.day) < (nasc.month, nasc.day))


def verificar(empresa, hoje: date | None = None) -> list[Alerta]:
    from esocial.models import Evento
    from esocial.servico import chave_admissao

    hoje = hoje or timezone.localdate()
    alertas: list[Alerta] = []
    tab = tabelas_do_ano(hoje.year)

    # --- Configuração -----------------------------------------------------
    if not tabela_atualizada(hoje.year):
        alertas.append(Alerta(
            CRITICO, f"Tabelas de INSS/IRRF de {hoje.year} não cadastradas",
            f"O cálculo está usando as tabelas de {tab.ano}. Os descontos podem estar errados.",
            "Portaria Interministerial MPS/MF anual; Lei 7.713/1988 (IRRF)",
        ))
    if not empresa.tem_certificado:
        alertas.append(Alerta(
            CRITICO, "Certificado digital não cadastrado",
            "Sem o certificado A1 nada pode ser enviado ao eSocial.",
            "Manual de Orientação do eSocial (assinatura digital obrigatória)",
            reverse("empresas:certificado", args=[empresa.pk]), "Enviar certificado",
        ))

    # --- Eventos com problema ---------------------------------------------
    problemas = Evento.objects.filter(empresa=empresa, status__in=["erro", "rejeitado"]).count()
    if problemas:
        alertas.append(Alerta(
            CRITICO, f"{problemas} evento(s) do eSocial com erro ou rejeitado(s)",
            "Enquanto não forem corrigidos, as informações não chegam à DCTFWeb e ao FGTS Digital.",
            "Lei 8.212/1991, art. 32-A (multa por omissão/atraso de informação)",
            reverse("esocial:eventos") + "?status=rejeitado", "Ver e corrigir",
        ))

    # --- Funcionários -----------------------------------------------------
    aceitas = set(Evento.objects.filter(empresa=empresa, tipo="S-2200").exclude(
        status__in=["erro", "rejeitado"]).values_list("chave", flat=True))
    for f in Funcionario.objects.filter(empresa=empresa, data_desligamento__isnull=True).select_related("cargo"):
        url = reverse("pessoal:detalhe", args=[f.pk])
        if not f.esocial_ja_cadastrado and chave_admissao(f) not in aceitas:
            atrasado = f.data_admissao <= hoje
            alertas.append(Alerta(
                CRITICO if atrasado else ATENCAO,
                f"{f.nome}: admissão (S-2200) não enviada",
                "Prazo: até o dia anterior ao início das atividades."
                + (" O prazo já passou." if atrasado else f" Início em {f.data_admissao:%d/%m/%Y}."),
                "CLT art. 41 e art. 47 (multa por empregado não registrado); Portaria MTP 671/2021",
                url, "Abrir funcionário",
            ))
        minimo = tab.salario_minimo * Decimal(f.horas_semanais) / 44
        if f.salario < c.r2(minimo):
            alertas.append(Alerta(
                CRITICO, f"{f.nome}: salário abaixo do mínimo",
                f"R$ {f.salario} para {f.horas_semanais}h semanais; mínimo proporcional R$ {c.r2(minimo)}.",
                "Constituição Federal, art. 7º, IV; OJ 358 da SDI-1/TST", url, "Corrigir salário",
            ))
        if f.horas_semanais > 44:
            alertas.append(Alerta(
                CRITICO, f"{f.nome}: jornada contratual acima de 44h semanais",
                "A duração normal do trabalho não pode passar de 44 horas por semana.",
                "Constituição Federal, art. 7º, XIII", url, "Corrigir jornada",
            ))
        idade = _idade(f.data_nascimento, hoje)
        if f.aprendiz and not 14 <= idade < 24:
            alertas.append(Alerta(CRITICO, f"{f.nome}: idade incompatível com aprendizagem",
                                  f"Aprendiz deve ter entre 14 e 24 anos (tem {idade}).", "CLT art. 428", url,
                                  "Revisar contrato"))
        elif not f.aprendiz and idade < 16:
            alertas.append(Alerta(CRITICO, f"{f.nome}: menor de 16 anos fora de aprendizagem",
                                  "Proibido trabalho de menores de 16 anos, salvo como aprendiz a partir de 14.",
                                  "Constituição Federal, art. 7º, XXXIII; CLT art. 403", url, "Revisar contrato"))

        # Férias vencidas / a vencer (período concessivo de 12 meses — CLT arts. 134 e 137)
        tiradas = set(f.ferias.exclude(status="cancelada").values_list("aquisitivo_inicio", flat=True))
        periodos = periodos_aquisitivos(f.data_admissao, hoje)
        for ini, fim in periodos[-2:]:
            if ini in tiradas:
                continue
            limite = _somar_meses(fim, 12)
            if limite < hoje:
                alertas.append(Alerta(
                    CRITICO, f"{f.nome}: férias vencidas ({ini:%d/%m/%Y} a {fim:%d/%m/%Y})",
                    f"O prazo para conceder terminou em {limite:%d/%m/%Y}: as férias são devidas em dobro. "
                    "Se já foram concedidas em outro sistema, cadastre-as aqui.",
                    "CLT art. 137", reverse("folha:ferias_nova") + f"?funcionario={f.pk}", "Programar férias",
                ))
            elif limite <= hoje + timedelta(days=90):
                alertas.append(Alerta(
                    ATENCAO, f"{f.nome}: férias precisam começar até {limite - timedelta(days=30):%d/%m/%Y}",
                    f"Período aquisitivo {ini:%d/%m/%Y}–{fim:%d/%m/%Y}; concessão até {limite:%d/%m/%Y}.",
                    "CLT arts. 134 e 137", reverse("folha:ferias_nova") + f"?funcionario={f.pk}",
                    "Programar férias",
                ))

    # --- Férias programadas -------------------------------------------------
    for fe in Ferias.objects.filter(funcionario__empresa=empresa, inicio__gte=hoje - timedelta(days=60)).exclude(
        status="cancelada"
    ).select_related("funcionario"):
        alertas += [Alerta(n, f"Férias de {fe.funcionario.nome}: {t}", d, b,
                           reverse("folha:ferias_detalhe", args=[fe.pk]), "Abrir férias")
                    for n, t, d, b in problemas_ferias(fe)]

    # --- 13º salário ----------------------------------------------------------
    ativos = Funcionario.objects.filter(empresa=empresa, data_desligamento__isnull=True).exists()
    if ativos and hoje.month in (10, 11):
        tem_adiant = Competencia.objects.filter(
            empresa=empresa, ano=hoje.year, data_adiantamento_13__isnull=False).exists()
        if not tem_adiant:
            alertas.append(Alerta(
                CRITICO if hoje > date(hoje.year, 11, 30) else ATENCAO,
                "1ª parcela do 13º salário não programada",
                "Deve ser paga até 30 de novembro (ou nas férias, se o empregado pediu em janeiro). "
                "Informe a data na folha de novembro.",
                "Lei 4.749/1965, art. 2º", reverse("folha:competencias"), "Abrir folhas",
            ))
    if ativos and hoje.month == 12:
        fechado = Competencia.objects.filter(empresa=empresa, tipo="13", ano=hoje.year, status="fechada").exists()
        if not fechado:
            alertas.append(Alerta(
                CRITICO if hoje.day > 20 else ATENCAO, "2ª parcela do 13º salário pendente",
                "Pagamento até 20 de dezembro; INSS e IRRF do 13º vencem também em 20/12.",
                "Lei 4.749/1965, art. 1º; Lei 8.212/1991, art. 30", reverse("folha:decimo_terceiro"),
                "Apurar 13º",
            ))

    # --- Folha mensal e prazos do eSocial -------------------------------------
    anterior = _somar_meses(date(hoje.year, hoje.month, 1), -1)
    comp_ant = Competencia.objects.filter(empresa=empresa, tipo="mensal", ano=anterior.year,
                                          mes=anterior.month).first()
    if ativos and (comp_ant is None or comp_ant.status != "fechada"):
        alertas.append(Alerta(
            CRITICO if hoje.day > 15 else ATENCAO,
            f"Folha de {anterior:%m/%Y} não fechada no eSocial",
            "Os eventos periódicos (S-1200, S-1210, S-1299) devem ser enviados até o dia 15 do mês seguinte.",
            "Manual de Orientação do eSocial — prazos dos eventos periódicos",
            reverse("folha:competencia", args=[comp_ant.pk]) if comp_ant else reverse("folha:competencia_nova"),
            "Apurar folha",
        ))
    for comp in Competencia.objects.filter(empresa=empresa, tipo="mensal").exclude(status="fechada"):
        limite = c.quinto_dia_util(*(_somar_meses(comp.inicio, 1).year, _somar_meses(comp.inicio, 1).month))
        if comp.data_pagamento > limite:
            alertas.append(Alerta(
                CRITICO, f"Folha {comp}: pagamento depois do 5º dia útil",
                f"Data informada {comp.data_pagamento:%d/%m/%Y}; limite {limite:%d/%m/%Y}.",
                "CLT art. 459, §1º", reverse("folha:competencia", args=[comp.pk]), "Ajustar data",
            ))

    # --- Guias -----------------------------------------------------------------
    for g in Guia.objects.filter(empresa=empresa).exclude(status="paga").select_related("competencia"):
        if g.vencimento < hoje:
            alertas.append(Alerta(
                CRITICO, f"{g.get_tipo_display()} de {g.competencia} vencida em {g.vencimento:%d/%m/%Y}",
                "Pague com multa e juros e marque como paga no sistema.",
                "Lei 9.430/1996, art. 61 (DARF); Lei 8.036/1990, art. 22 (FGTS)",
                reverse("folha:guias", args=[g.competencia_id]), "Ver guias",
            ))
        elif g.vencimento <= hoje + timedelta(days=5):
            alertas.append(Alerta(
                ATENCAO, f"{g.get_tipo_display()} de {g.competencia} vence em {g.vencimento:%d/%m/%Y}",
                "Emita e pague a guia.", "Lei 8.212/1991, art. 30; Lei 8.036/1990, art. 15",
                reverse("folha:guias", args=[g.competencia_id]), "Emitir guia",
            ))

    return sorted(alertas, key=lambda a: a.ordem)


def problemas_ferias(fe: Ferias) -> list[tuple[str, str, str, str]]:
    """Regras da CLT para a programação de férias: (nível, título, detalhe, base legal)."""
    saida = []
    direito = c.dias_direito_ferias(fe.faltas_injustificadas)
    outras = Ferias.objects.filter(funcionario=fe.funcionario, aquisitivo_inicio=fe.aquisitivo_inicio).exclude(
        status="cancelada")
    if fe.pk:
        outras = outras.exclude(pk=fe.pk)
    fracoes = list(outras.values_list("dias", flat=True)) + [fe.dias]
    if sum(fracoes) + fe.dias_abono > direito:
        saida.append((CRITICO, "dias acima do direito",
                      f"{sum(fracoes)} dias de gozo no período + {fe.dias_abono} vendidos > {direito} dias de direito.",
                      "CLT art. 130"))
    if fe.dias_abono * 3 > direito:
        saida.append((CRITICO, "abono acima de 1/3", f"Só é possível vender até {direito // 3} dias.",
                      "CLT art. 143"))
    if fe.dias < 5:
        saida.append((CRITICO, "período menor que 5 dias",
                      "Nenhum período de férias pode ter menos de 5 dias corridos.", "CLT art. 134, §1º"))
    if len(fracoes) > 3:
        saida.append((CRITICO, "mais de 3 períodos", "As férias podem ser divididas em até 3 períodos.",
                      "CLT art. 134, §1º"))
    if len(fracoes) > 1 and max(fracoes) < 14 and sum(fracoes) + fe.dias_abono >= direito:
        saida.append((CRITICO, "nenhum período com 14 dias ou mais",
                      "Quando fracionadas, um dos períodos deve ter pelo menos 14 dias.", "CLT art. 134, §1º"))
    if fe.inicio.weekday() in (4, 5):
        saida.append((ATENCAO, "início nos 2 dias antes do repouso semanal",
                      "É proibido iniciar as férias nos dois dias que antecedem feriado ou o descanso semanal.",
                      "CLT art. 134, §3º"))
    if fe.data_pagamento > fe.inicio - timedelta(days=2):
        saida.append((CRITICO, "pagamento fora do prazo",
                      f"Deve ser pago até {fe.inicio - timedelta(days=2):%d/%m/%Y} (2 dias antes do início); "
                      "atraso gera pagamento em dobro.", "CLT art. 145; Súmula 450 TST"))
    if fe.data_aviso > fe.inicio - timedelta(days=30):
        saida.append((ATENCAO, "aviso com menos de 30 dias",
                      f"O aviso deveria ter sido dado até {fe.inicio - timedelta(days=30):%d/%m/%Y}.", "CLT art. 135"))
    limite = _somar_meses(fe.aquisitivo_fim, 12)
    if fe.fim > limite:
        saida.append((CRITICO, "gozo após o período concessivo",
                      f"Os dias após {limite:%d/%m/%Y} são devidos em dobro.", "CLT art. 137"))
    if fe.inicio <= fe.aquisitivo_fim:
        saida.append((ATENCAO, "férias antes de completar o período aquisitivo",
                      "Só é permitido em férias coletivas.", "CLT arts. 130 e 140"))
    return saida
