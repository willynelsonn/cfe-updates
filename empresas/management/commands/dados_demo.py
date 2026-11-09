"""Cria uma empresa, funcionários e uma folha de exemplo para conhecer o sistema."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from empresas.models import Empresa
from folha.models import Competencia, Ferias, Lancamento, Rubrica, criar_rubricas_padrao
from folha.servico import calcular_competencia, calcular_ferias
from pessoal.models import Cargo, Dependente, Funcionario


class Command(BaseCommand):
    help = "Cria dados de demonstração (empresa fictícia, 3 funcionários, folhas de 10 e 11/2026 e férias)."

    def handle(self, *args, **opts):
        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "", "admin")
            self.stdout.write(self.style.WARNING("Usuário admin / senha admin criado. Troque a senha!"))

        emp, _ = Empresa.objects.get_or_create(
            nr_insc="11222333000181",
            defaults=dict(
                razao_social="Padaria Pão Quente LTDA (DEMONSTRAÇÃO)", nome_fantasia="Padaria Pão Quente",
                class_trib="99", cnae="1091102", cnpj_sindicato="11444777000161", municipio="São Paulo", uf="SP",
            ),
        )
        criar_rubricas_padrao(emp)
        padeiro, _ = Cargo.objects.get_or_create(empresa=emp, nome="Padeiro", defaults={"cbo": "848305"})
        atendente, _ = Cargo.objects.get_or_create(empresa=emp, nome="Atendente de lanchonete", defaults={"cbo": "513435"})
        gerente, _ = Cargo.objects.get_or_create(empresa=emp, nome="Gerente de loja", defaults={"cbo": "141410"})

        base = dict(empresa=emp, cep="01310100", logradouro="Avenida Paulista", numero="1000", bairro="Bela Vista",
                    cod_municipio="3550308", uf="SP", grau_instrucao="07", raca_cor=3)
        pessoas = [
            dict(matricula="0001", nome="Maria da Silva", cpf="52998224725", data_nascimento=date(1990, 5, 10), sexo="F",
                 data_admissao=date(2025, 3, 1), cargo=padeiro, salario=Decimal("3000"), vale_transporte=Decimal("220")),
            dict(matricula="0002", nome="José Souza", cpf="11144477735", data_nascimento=date(1998, 8, 2), sexo="M",
                 data_admissao=date(2025, 6, 2), cargo=atendente, salario=Decimal("1700")),
            dict(matricula="0003", nome="Ana Pereira", cpf="12345678909", data_nascimento=date(1985, 1, 20), sexo="F",
                 data_admissao=date(2025, 1, 10), cargo=gerente, salario=Decimal("6500")),
        ]
        funcs = {}
        for p in pessoas:
            f, _ = Funcionario.objects.get_or_create(empresa=emp, matricula=p["matricula"], defaults={**base, **p})
            funcs[p["matricula"]] = f
        Dependente.objects.get_or_create(
            funcionario=funcs["0002"], nome="Pedro Souza",
            defaults=dict(data_nascimento=date(2021, 4, 4), tipo="03", dependente_irrf=True, dependente_salario_familia=True),
        )

        comp, criada = Competencia.objects.get_or_create(empresa=emp, ano=2026, mes=10,
                                                         defaults={"data_pagamento": date(2026, 11, 5)})
        if not Ferias.objects.filter(funcionario=funcs["0001"]).exists():
            fe = Ferias.objects.create(
                funcionario=funcs["0001"], aquisitivo_inicio=date(2025, 3, 1), aquisitivo_fim=date(2026, 2, 28),
                inicio=date(2026, 12, 7), dias=20, dias_abono=10, data_pagamento=date(2026, 12, 4),
                data_aviso=date(2026, 11, 6),
            )
            calcular_ferias(fe)
        Competencia.objects.get_or_create(
            empresa=emp, ano=2026, mes=11,
            defaults={"data_pagamento": date(2026, 12, 4), "data_adiantamento_13": date(2026, 11, 27)},
        )
        if criada:
            he = Rubrica.objects.get(empresa=emp, papel="he50")
            faltas = Rubrica.objects.get(empresa=emp, papel="faltas")
            Lancamento.objects.create(competencia=comp, funcionario=funcs["0001"], rubrica=he, quantidade=Decimal("12"))
            Lancamento.objects.create(competencia=comp, funcionario=funcs["0002"], rubrica=faltas, quantidade=Decimal("1"))
            calcular_competencia(comp)
        self.stdout.write(self.style.SUCCESS(f"Pronto: {emp} com {len(funcs)} funcionários e a folha {comp}."))
