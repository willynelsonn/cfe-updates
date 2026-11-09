from datetime import date
from decimal import Decimal

from django.db import models

from empresas.models import Empresa
from empresas.validators import formatar_cpf, so_digitos, validar_cpf

UFS = [(u, u) for u in "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()]


class Cargo(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="cargos")
    nome = models.CharField(max_length=100)
    cbo = models.CharField("CBO", max_length=6, help_text="Código Brasileiro de Ocupações (6 dígitos)")

    class Meta:
        ordering = ["nome"]
        unique_together = [("empresa", "nome")]

    def __str__(self):
        return f"{self.nome} (CBO {self.cbo})"


class Funcionario(models.Model):
    SEXO = [("M", "Masculino"), ("F", "Feminino")]
    RACA_COR = [
        (1, "Branca"), (2, "Preta"), (3, "Parda"), (4, "Amarela"), (5, "Indígena"), (6, "Não informado"),
    ]
    ESTADO_CIVIL = [
        (1, "Solteiro(a)"), (2, "Casado(a)"), (3, "Divorciado(a)"), (4, "Separado(a)"), (5, "Viúvo(a)"),
    ]
    GRAU_INSTRUCAO = [
        ("01", "Analfabeto"),
        ("02", "Até o 5º ano incompleto do ensino fundamental"),
        ("03", "5º ano completo do ensino fundamental"),
        ("04", "Do 6º ao 9º ano do ensino fundamental incompleto"),
        ("05", "Ensino fundamental completo"),
        ("06", "Ensino médio incompleto"),
        ("07", "Ensino médio completo"),
        ("08", "Educação superior incompleta"),
        ("09", "Educação superior completa"),
        ("10", "Pós-graduação completa"),
        ("11", "Mestrado completo"),
        ("12", "Doutorado completo"),
    ]
    CATEGORIA = [
        ("101", "101 - Empregado geral"),
        ("103", "103 - Aprendiz"),
        ("104", "104 - Empregado doméstico"),
        ("105", "105 - Contrato por prazo determinado (Lei 9.601/1998)"),
        ("106", "106 - Trabalhador temporário (Lei 6.019/1974)"),
        ("111", "111 - Contrato de trabalho intermitente"),
    ]
    TIPO_CONTRATO = [(1, "Prazo indeterminado"), (2, "Prazo determinado (em dias)"), (3, "Prazo determinado (por ocorrência)")]
    TIPO_JORNADA = [
        (2, "Jornada 12x36"),
        (3, "Jornada com horário diário fixo e folga fixa (domingo)"),
        (4, "Jornada com horário diário fixo e folga fixa (exceto domingo)"),
        (5, "Jornada com horário diário fixo e folga fixa (outro dia)"),
        (6, "Turno ininterrupto de revezamento"),
        (7, "Demais tipos de jornada"),
        (9, "Outros"),
    ]
    INSALUBRIDADE = [(0, "Não"), (10, "Grau mínimo (10%)"), (20, "Grau médio (20%)"), (40, "Grau máximo (40%)")]
    MOTIVO_DESLIGAMENTO = [
        ("01", "01 - Rescisão com justa causa, por iniciativa do empregador"),
        ("02", "02 - Rescisão sem justa causa, por iniciativa do empregador"),
        ("03", "03 - Rescisão antecipada do contrato a termo por iniciativa do empregador"),
        ("04", "04 - Rescisão antecipada do contrato a termo por iniciativa do empregado"),
        ("05", "05 - Rescisão por culpa recíproca"),
        ("06", "06 - Rescisão por término do contrato a termo"),
        ("07", "07 - Rescisão do contrato de trabalho por iniciativa do empregado (pedido de demissão)"),
        ("08", "08 - Rescisão por interesse do empregado (art. 394-A CLT)"),
        ("10", "10 - Rescisão por falecimento do empregado"),
        ("33", "33 - Rescisão por acordo entre as partes (art. 484-A CLT)"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="funcionarios")
    matricula = models.CharField("matrícula", max_length=30)

    # Dados pessoais
    nome = models.CharField(max_length=70)
    cpf = models.CharField("CPF", max_length=14, validators=[validar_cpf])
    data_nascimento = models.DateField("data de nascimento")
    sexo = models.CharField(max_length=1, choices=SEXO)
    raca_cor = models.PositiveSmallIntegerField("raça/cor", choices=RACA_COR, default=6)
    estado_civil = models.PositiveSmallIntegerField(choices=ESTADO_CIVIL, null=True, blank=True)
    grau_instrucao = models.CharField("grau de instrução", max_length=2, choices=GRAU_INSTRUCAO, default="07")
    nome_social = models.CharField(max_length=70, blank=True)

    # Endereço
    cep = models.CharField("CEP", max_length=9)
    logradouro = models.CharField(max_length=100)
    numero = models.CharField("número", max_length=10, default="S/N")
    complemento = models.CharField(max_length=30, blank=True)
    bairro = models.CharField(max_length=90, blank=True)
    cod_municipio = models.CharField("código IBGE do município", max_length=7)
    uf = models.CharField("UF", max_length=2, choices=UFS)

    telefone = models.CharField(max_length=13, blank=True)
    email = models.EmailField("e-mail", blank=True)

    # Contrato
    data_admissao = models.DateField("data de admissão")
    categoria = models.CharField("categoria eSocial", max_length=3, choices=CATEGORIA, default="101")
    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name="funcionarios")
    salario = models.DecimalField("salário mensal", max_digits=12, decimal_places=2)
    tipo_contrato = models.PositiveSmallIntegerField(choices=TIPO_CONTRATO, default=1)
    data_termino = models.DateField("término do contrato", null=True, blank=True)
    horas_semanais = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("44"))
    tipo_jornada = models.PositiveSmallIntegerField(choices=TIPO_JORNADA, default=3)
    descricao_jornada = models.CharField(
        "descrição da jornada", max_length=200, default="Segunda a sexta 08:00-17:00 (1h intervalo), sábado 08:00-12:00"
    )
    insalubridade = models.PositiveSmallIntegerField(choices=INSALUBRIDADE, default=0)
    periculosidade = models.BooleanField(default=False, help_text="Adicional de 30% sobre o salário-base")
    vale_transporte = models.DecimalField(
        "vale-transporte mensal (R$)", max_digits=10, decimal_places=2, default=Decimal("0"),
        help_text="Custo mensal do VT. Desconto de até 6% do salário-base.",
    )

    # Pagamento
    banco = models.CharField(max_length=3, blank=True)
    agencia = models.CharField("agência", max_length=10, blank=True)
    conta = models.CharField(max_length=20, blank=True)
    chave_pix = models.CharField("chave PIX", max_length=80, blank=True)

    # Desligamento
    data_desligamento = models.DateField("data de desligamento", null=True, blank=True)
    motivo_desligamento = models.CharField(max_length=2, choices=MOTIVO_DESLIGAMENTO, blank=True)
    aviso_previo_indenizado = models.BooleanField("aviso prévio indenizado", default=False)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "funcionário"
        constraints = [
            models.UniqueConstraint(fields=["empresa", "matricula"], name="matricula_unica_por_empresa"),
        ]

    def __str__(self):
        return f"{self.matricula} - {self.nome}"

    def save(self, *args, **kwargs):
        self.cpf = so_digitos(self.cpf)
        self.cep = so_digitos(self.cep)
        self.telefone = so_digitos(self.telefone)
        super().save(*args, **kwargs)

    @property
    def cpf_formatado(self):
        return formatar_cpf(self.cpf)

    @property
    def ativo(self):
        return self.data_desligamento is None

    def ativo_na_competencia(self, ano: int, mes: int) -> bool:
        inicio = date(ano, mes, 1)
        fim = date(ano + (mes == 12), mes % 12 + 1, 1)
        if self.data_admissao >= fim:
            return False
        return self.data_desligamento is None or self.data_desligamento >= inicio

    @property
    def aprendiz(self):
        return self.categoria == "103"


class Dependente(models.Model):
    TIPO = [
        ("01", "Cônjuge"),
        ("02", "Companheiro(a) com quem tenha filho ou viva há mais de 5 anos"),
        ("03", "Filho(a) ou enteado(a)"),
        ("04", "Filho(a) ou enteado(a) universitário(a) ou cursando escola técnica, até 24 anos"),
        ("06", "Irmão(ã), neto(a) ou bisneto(a) sem arrimo dos pais, do(a) qual detenha a guarda judicial"),
        ("09", "Pais, avós e bisavós"),
        ("10", "Menor pobre do qual detenha a guarda judicial"),
        ("11", "A pessoa absolutamente incapaz, da qual seja tutor ou curador"),
        ("12", "Ex-cônjuge"),
        ("99", "Agregado/Outros"),
    ]

    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name="dependentes")
    nome = models.CharField(max_length=70)
    cpf = models.CharField("CPF", max_length=14, blank=True, validators=[validar_cpf])
    data_nascimento = models.DateField("data de nascimento")
    tipo = models.CharField(max_length=2, choices=TIPO, default="03")
    sexo = models.CharField(max_length=1, choices=Funcionario.SEXO, blank=True)
    dependente_irrf = models.BooleanField("dependente para IRRF", default=True)
    dependente_salario_familia = models.BooleanField("dependente para salário-família", default=False)
    incapaz = models.BooleanField("incapaz para o trabalho", default=False)

    class Meta:
        ordering = ["data_nascimento"]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.cpf = so_digitos(self.cpf)
        super().save(*args, **kwargs)

    def idade_em(self, data: date) -> int:
        n = self.data_nascimento
        return data.year - n.year - ((data.month, data.day) < (n.month, n.day))

    def da_direito_salario_familia(self, data: date) -> bool:
        return self.dependente_salario_familia and (self.idade_em(data) < 14 or self.incapaz)
