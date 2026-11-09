"""Tabelas legais usadas no cálculo da folha.

ATENÇÃO: estes valores mudam todo ano (normalmente em janeiro). Ao virar o ano,
acrescente a tabela nova aqui e confira na fonte oficial (Portaria Interministerial
MPS/MF, Receita Federal e Decreto do salário mínimo).

2026:
- Salário mínimo R$ 1.621,00 (Decreto 12.797/2025).
- INSS: Portaria Interministerial MPS/MF nº 13/2026 (teto R$ 8.475,55).
- IRRF: tabela progressiva vigente desde 05/2025 + redução da Lei 15.270/2025
  (isenção efetiva até R$ 5.000,00 e redução parcial até R$ 7.350,00).
- Salário-família: cota R$ 67,54 para remuneração até R$ 1.980,38.
"""

from dataclasses import dataclass, field
from decimal import Decimal as D


@dataclass(frozen=True)
class FaixaINSS:
    ate: D
    aliquota: D  # em percentual


@dataclass(frozen=True)
class FaixaIRRF:
    ate: D | None  # None = acima da última faixa
    aliquota: D
    deducao: D


@dataclass(frozen=True)
class RedutorIRRF:
    """Redução mensal do IRRF (Lei 15.270/2025)."""

    limite_isencao: D  # até este rendimento, reduz até ``reducao_maxima``
    reducao_maxima: D
    limite_parcial: D  # entre limite_isencao e este valor, redução linear
    constante: D
    fator: D


@dataclass(frozen=True)
class TabelasAno:
    ano: int
    salario_minimo: D
    inss: list[FaixaINSS]
    irrf: list[FaixaIRRF]
    deducao_dependente_irrf: D
    desconto_simplificado_irrf: D
    salario_familia_cota: D
    salario_familia_limite: D
    redutor_irrf: RedutorIRRF | None = None
    fgts_aliquota: D = D("8")
    fgts_aliquota_aprendiz: D = D("2")
    cpp_patronal: D = D("20")
    irrf_minimo_retencao: D = D("10.00")
    observacoes: list[str] = field(default_factory=list)

    @property
    def teto_inss(self) -> D:
        return self.inss[-1].ate


_IRRF_DESDE_MAIO_2025 = [
    FaixaIRRF(D("2428.80"), D("0"), D("0")),
    FaixaIRRF(D("2826.65"), D("7.5"), D("182.16")),
    FaixaIRRF(D("3751.05"), D("15"), D("394.16")),
    FaixaIRRF(D("4664.68"), D("22.5"), D("675.49")),
    FaixaIRRF(None, D("27.5"), D("908.73")),
]

TABELAS: dict[int, TabelasAno] = {
    2025: TabelasAno(
        ano=2025,
        salario_minimo=D("1518.00"),
        inss=[
            FaixaINSS(D("1518.00"), D("7.5")),
            FaixaINSS(D("2793.88"), D("9")),
            FaixaINSS(D("4190.83"), D("12")),
            FaixaINSS(D("8157.41"), D("14")),
        ],
        irrf=_IRRF_DESDE_MAIO_2025,
        deducao_dependente_irrf=D("189.59"),
        desconto_simplificado_irrf=D("607.20"),
        salario_familia_cota=D("65.00"),
        salario_familia_limite=D("1906.04"),
        observacoes=["Tabela de IRRF de 2025 válida a partir de maio/2025."],
    ),
    2026: TabelasAno(
        ano=2026,
        salario_minimo=D("1621.00"),
        inss=[
            FaixaINSS(D("1621.00"), D("7.5")),
            FaixaINSS(D("2902.84"), D("9")),
            FaixaINSS(D("4354.27"), D("12")),
            FaixaINSS(D("8475.55"), D("14")),
        ],
        irrf=_IRRF_DESDE_MAIO_2025,
        deducao_dependente_irrf=D("189.59"),
        desconto_simplificado_irrf=D("607.20"),
        salario_familia_cota=D("67.54"),
        salario_familia_limite=D("1980.38"),
        redutor_irrf=RedutorIRRF(
            limite_isencao=D("5000.00"),
            reducao_maxima=D("312.89"),
            limite_parcial=D("7350.00"),
            constante=D("978.62"),
            fator=D("0.133145"),
        ),
    ),
}


def tabelas_do_ano(ano: int) -> TabelasAno:
    """Retorna a tabela do ano; se não houver, usa a mais recente anterior (e avisa na tela)."""
    if ano in TABELAS:
        return TABELAS[ano]
    anteriores = [a for a in TABELAS if a <= ano]
    if not anteriores:
        raise ValueError(f"Não há tabelas legais cadastradas para {ano}.")
    return TABELAS[max(anteriores)]


def tabela_atualizada(ano: int) -> bool:
    return ano in TABELAS
