"""Dados de exemplo para os testes."""

from datetime import date
from decimal import Decimal

from empresas.models import Empresa
from folha.models import Competencia, criar_rubricas_padrao
from pessoal.models import Cargo, Dependente, Funcionario


def empresa(**kw) -> Empresa:
    dados = dict(
        razao_social="Padaria Exemplo LTDA",
        nr_insc="11.222.333/0001-81",
        class_trib="99",
        cnae="1091102",
        cnpj_sindicato="11.444.777/0001-61",
        inicio_esocial="2026-01",
    )
    dados.update(kw)
    e = Empresa.objects.create(**dados)
    criar_rubricas_padrao(e)
    return e


def funcionario(emp, **kw) -> Funcionario:
    cargo, _ = Cargo.objects.get_or_create(empresa=emp, nome="Padeiro", defaults={"cbo": "848305"})
    dados = dict(
        empresa=emp,
        matricula="0001",
        nome="Maria da Silva",
        cpf="529.982.247-25",
        data_nascimento=date(1990, 5, 10),
        sexo="F",
        raca_cor=3,
        estado_civil=2,
        grau_instrucao="07",
        cep="01310-100",
        logradouro="Avenida Paulista",
        numero="1000",
        bairro="Bela Vista",
        cod_municipio="3550308",
        uf="SP",
        telefone="11999990000",
        email="maria@example.com",
        data_admissao=date(2025, 3, 1),
        cargo=cargo,
        salario=Decimal("3000.00"),
    )
    dados.update(kw)
    return Funcionario.objects.create(**dados)


def filho(func, nascimento=date(2020, 1, 1), **kw) -> Dependente:
    dados = dict(
        funcionario=func, nome="João da Silva", cpf="111.444.777-35", data_nascimento=nascimento, tipo="03",
        sexo="M", dependente_irrf=True, dependente_salario_familia=True,
    )
    dados.update(kw)
    return Dependente.objects.create(**dados)


def competencia(emp, ano=2026, mes=10, **kw) -> Competencia:
    return Competencia.objects.create(empresa=emp, ano=ano, mes=mes, data_pagamento=date(2026, 11, 5), **kw)
