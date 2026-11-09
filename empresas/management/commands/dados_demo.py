"""Cria uma empresa fictícia com um ano de histórico para conhecer o sistema."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from empresas.models import Empresa
from folha.models import Competencia, Ferias, Lancamento, Rescisao, Rubrica, criar_rubricas_padrao
from folha.rescisao import calcular_rescisao
from folha.servico import calcular_competencia, calcular_ferias
from pessoal.models import Cargo, Dependente, Funcionario

PESSOAS = [
    # matrícula, nome, cpf, nascimento, sexo, admissão, cargo, salário, VT, benefícios, periculosidade
    ("0001", "Maria da Silva", "52998224725", date(1990, 5, 10), "F", date(2025, 3, 1), "Padeiro", "3000", "220", "450", False),
    ("0002", "José Souza", "11144477735", date(1998, 8, 2), "M", date(2025, 6, 2), "Atendente", "1700", "220", "450", False),
    ("0003", "Ana Pereira", "12345678909", date(1985, 1, 20), "F", date(2025, 1, 10), "Gerente de loja", "6500", "0", "900", False),
    ("0004", "Carlos Oliveira", "98765432100", date(1979, 11, 3), "M", date(2024, 9, 16), "Padeiro", "3200", "220", "450", False),
    ("0005", "Fernanda Lima", "39053344705", date(2001, 2, 14), "F", date(2026, 2, 2), "Atendente", "1750", "220", "450", False),
    ("0006", "Rafael Costa", "71428793860", date(1993, 7, 22), "M", date(2025, 11, 3), "Motorista de entregas", "2600", "0", "450", True),
    ("0007", "Juliana Rocha", "87748248800", date(1996, 4, 5), "F", date(2026, 5, 4), "Confeiteiro", "2400", "220", "450", False),
]
CARGOS = {"Padeiro": "848305", "Atendente": "513435", "Gerente de loja": "141410",
          "Motorista de entregas": "782310", "Confeiteiro": "848310"}


class Command(BaseCommand):
    help = "Cria dados de demonstração: padaria fictícia, 8 funcionários e folhas de jan a out/2026."

    @transaction.atomic
    def handle(self, *args, **opts):
        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "", "admin", first_name="Administrador")
            self.stdout.write(self.style.WARNING("Usuário admin / senha admin criado. Troque a senha!"))
        if Empresa.objects.filter(nr_insc="11222333000181").exists():
            self.stdout.write("Dados de demonstração já existem.")
            return

        emp = Empresa.objects.create(
            nr_insc="11222333000181", razao_social="Padaria Pão Quente LTDA (DEMONSTRAÇÃO)",
            nome_fantasia="Padaria Pão Quente", class_trib="99", cnae="1091102", aliq_rat=2,
            esocial_ja_iniciado=True,  # simula empresa migrada de outro sistema (ex.: Domínio)
            cnpj_sindicato="11444777000161", municipio="São Paulo", uf="SP",
        )
        criar_rubricas_padrao(emp)
        cargos = {n: Cargo.objects.create(empresa=emp, nome=n, cbo=cbo) for n, cbo in CARGOS.items()}
        base = dict(empresa=emp, cep="01310100", logradouro="Avenida Paulista", numero="1000", bairro="Bela Vista",
                    cod_municipio="3550308", uf="SP", grau_instrucao="07", raca_cor=3)
        funcs = {}
        for mat, nome, cpf, nasc, sexo, adm, cargo, sal, vt, ben, peric in PESSOAS:
            funcs[mat] = Funcionario.objects.create(
                matricula=mat, nome=nome, cpf=cpf, data_nascimento=nasc, sexo=sexo, data_admissao=adm,
                cargo=cargos[cargo], salario=Decimal(sal), vale_transporte=Decimal(vt),
                beneficios_mensais=Decimal(ben), periculosidade=peric,
                esocial_ja_cadastrado=adm.year < 2026, **base,
            )
        # Funcionário desligado em julho (para o histórico de rescisões)
        saiu = Funcionario.objects.create(
            matricula="0008", nome="Pedro Alves", cpf="85361847011", data_nascimento=date(1988, 9, 9), sexo="M",
            data_admissao=date(2024, 2, 5), cargo=cargos["Atendente"], salario=Decimal("1700"),
            vale_transporte=Decimal("220"), esocial_ja_cadastrado=True, **base,
        )
        # Férias já tiradas (registradas para o controle de períodos aquisitivos)
        for f, ini, gozo in ((funcs["0004"], date(2024, 9, 16), date(2025, 10, 6)),
                             (saiu, date(2024, 2, 5), date(2025, 3, 10)),
                             (funcs["0003"], date(2025, 1, 10), date(2026, 3, 2))):
            antigas = Ferias.objects.create(
                funcionario=f, aquisitivo_inicio=ini, aquisitivo_fim=date(ini.year + 1, ini.month, ini.day) - timedelta(days=1),
                inicio=gozo, dias=30, data_pagamento=gozo - timedelta(days=3), data_aviso=gozo - timedelta(days=30),
            )
            calcular_ferias(antigas)
        Dependente.objects.create(funcionario=funcs["0002"], nome="Pedro Souza", data_nascimento=date(2021, 4, 4),
                                  tipo="03", dependente_irrf=True, dependente_salario_familia=True)
        Dependente.objects.create(funcionario=funcs["0004"], nome="Lucas Oliveira", data_nascimento=date(2012, 6, 1),
                                  tipo="03", dependente_irrf=True)

        he = Rubrica.objects.get(empresa=emp, papel="he50")
        for mes in range(1, 11):
            comp = Competencia.objects.create(
                empresa=emp, ano=2026, mes=mes, data_pagamento=date(2026 + (mes == 12), mes % 12 + 1, 5),
            )
            for i, mat in enumerate(("0001", "0004", "0006")):
                horas = Decimal((mes * (i + 3)) % 9 + 2)
                if funcs[mat].data_admissao <= comp.fim:
                    Lancamento.objects.create(competencia=comp, funcionario=funcs[mat], rubrica=he, quantidade=horas)
            if mes == 7:
                resc = Rescisao.objects.create(
                    funcionario=saiu, motivo="02", tipo_aviso="indenizado", data_aviso=date(2026, 7, 17),
                    data_desligamento=date(2026, 7, 17), data_pagamento=date(2026, 7, 24),
                    saldo_fgts=Decimal("3600"),
                )
                calcular_rescisao(resc)
            calcular_competencia(comp)
            if mes < 10:
                comp.status = "fechada"
                comp.save(update_fields=["status"])

        fe = Ferias.objects.create(
            funcionario=funcs["0001"], aquisitivo_inicio=date(2025, 3, 1), aquisitivo_fim=date(2026, 2, 28),
            inicio=date(2026, 12, 7), dias=20, dias_abono=10, data_pagamento=date(2026, 12, 4),
            data_aviso=date(2026, 11, 6),
        )
        calcular_ferias(fe)
        Competencia.objects.create(empresa=emp, ano=2026, mes=11, data_pagamento=date(2026, 12, 4),
                                   data_adiantamento_13=date(2026, 11, 27))
        self.stdout.write(self.style.SUCCESS(f"Pronto: {emp} com {len(funcs) + 1} funcionários e 10 folhas."))
