import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .cripto import cifrar, decifrar
from .validators import cnpj_valido, formatar_cnpj, normalizar_cnpj, so_digitos


def _storage_privado():
    if settings.FOLHA_ARQUIVOS_NO_BANCO:
        from .armazenamento import BancoStorage

        return BancoStorage()
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)


class ArquivoPrivado(models.Model):
    """Arquivo guardado no banco (certificados), para hospedagens sem disco permanente."""

    nome = models.CharField(max_length=255, unique=True)
    conteudo = models.BinaryField()
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "arquivo privado"
        verbose_name_plural = "arquivos privados"

    def __str__(self):
        return self.nome


def _caminho_certificado(instance, filename):
    return f"certificados/empresa_{instance.pk or 'nova'}_{Path(filename).name}"


class Empresa(models.Model):
    """Empregador. Um escritório pode ter várias empresas clientes."""

    TP_INSC = [(1, "CNPJ"), (2, "CPF")]
    CLASS_TRIB = [
        ("01", "01 - Simples Nacional (tributação previdenciária substituída)"),
        ("02", "02 - Simples Nacional (tributação previdenciária não substituída)"),
        ("03", "03 - Simples Nacional (substituída e não substituída concomitantemente)"),
        ("04", "04 - MEI"),
        ("99", "99 - Demais pessoas jurídicas (Lucro Real/Presumido)"),
    ]
    AMBIENTE = [(2, "Produção restrita (testes)"), (1, "Produção (valendo)")]

    razao_social = models.CharField("razão social", max_length=115)
    nome_fantasia = models.CharField("nome fantasia", max_length=115, blank=True)
    tp_insc = models.PositiveSmallIntegerField("tipo de inscrição", choices=TP_INSC, default=1)
    nr_insc = models.CharField("CNPJ/CPF", max_length=18, unique=True)
    class_trib = models.CharField("classificação tributária", max_length=2, choices=CLASS_TRIB, default="99")
    simples_anexo_iv = models.BooleanField(
        "Simples Nacional - Anexo IV",
        default=False,
        help_text="Empresas do Anexo IV recolhem a contribuição patronal (CPP) fora do DAS.",
    )
    cnae = models.CharField("CNAE preponderante", max_length=9, help_text="7 dígitos (ex.: 4711-3/02)")
    fpas = models.CharField("FPAS", max_length=3, default="515")
    cod_terceiros = models.CharField("código de terceiros", max_length=4, default="0115")
    aliq_terceiros = models.DecimalField(
        "alíquota de terceiros (%)", max_digits=5, decimal_places=2, default=Decimal("5.80")
    )
    aliq_rat = models.PositiveSmallIntegerField(
        "alíquota RAT (%)", choices=[(1, "1%"), (2, "2%"), (3, "3%")], default=1
    )
    fap = models.DecimalField(
        "FAP",
        max_digits=6,
        decimal_places=4,
        default=Decimal("1.0000"),
        validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(Decimal("2"))],
    )
    cnpj_sindicato = models.CharField(
        "CNPJ do sindicato da categoria", max_length=18, blank=True,
        help_text="Obrigatório no S-2200 (admissão).",
    )
    inicio_esocial = models.CharField(
        "início de validade no eSocial (AAAA-MM)", max_length=7, default="2026-01"
    )
    municipio = models.CharField(max_length=60, blank=True)
    uf = models.CharField("UF", max_length=2, blank=True)
    dia_pagamento = models.PositiveSmallIntegerField(
        "dia do pagamento do salário", default=5,
        help_text="Dia do mês seguinte em que o salário é pago (até o 5º dia útil).",
    )

    ambiente_esocial = models.PositiveSmallIntegerField("ambiente eSocial", choices=AMBIENTE, default=2)
    certificado = models.FileField(
        "certificado digital A1 (.pfx)", storage=_storage_privado, upload_to=_caminho_certificado, blank=True
    )
    certificado_senha_cifrada = models.TextField(blank=True, editable=False)
    transmissor_cnpj = models.CharField(
        "CNPJ/CPF do transmissor", max_length=18, blank=True,
        help_text="Quem assina e envia (o escritório contábil ou a própria empresa). Em branco = a própria empresa.",
    )

    envio_automatico = models.BooleanField(
        "envio automático ao eSocial", default=True,
        help_text="Gera e transmite sozinho os eventos ao salvar admissões, férias, desligamentos e ao apurar a folha.",
    )
    esocial_ja_iniciado = models.BooleanField(
        "empresa já cadastrada no eSocial por outro sistema", default=False,
        help_text="Marque se o S-1000/S-1005/S-1020 já foram enviados (ex.: pelo Domínio). "
                  "O FolhaWeb então só envia as rubricas próprias (S-1010).",
    )

    ativa = models.BooleanField(default=True)
    criada_em = models.DateTimeField(auto_now_add=True)

    # Cadastro aberto: a dona cadastra, o escritório confere e libera.
    SITUACAO = [("em_analise", "Em análise"), ("ativa", "Ativa"), ("recusada", "Recusada")]
    situacao = models.CharField("situação", max_length=10, choices=SITUACAO, default="ativa")
    motivo_recusa = models.TextField("motivo da recusa", blank=True)
    validada_em = models.DateTimeField(null=True, blank=True, editable=False)
    validada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+"
    )

    class Meta:
        ordering = ["razao_social"]
        verbose_name = "empresa"

    def __str__(self):
        return self.nome_fantasia or self.razao_social

    # --- dados derivados -------------------------------------------------
    def save(self, *args, **kwargs):
        self.nr_insc = normalizar_cnpj(self.nr_insc) if self.tp_insc == 1 else so_digitos(self.nr_insc)
        self.cnpj_sindicato = normalizar_cnpj(self.cnpj_sindicato)
        self.transmissor_cnpj = normalizar_cnpj(self.transmissor_cnpj)
        self.cnae = so_digitos(self.cnae)
        super().save(*args, **kwargs)

    @property
    def nr_insc_formatado(self):
        return formatar_cnpj(self.nr_insc) if self.tp_insc == 1 else self.nr_insc

    @property
    def nr_insc_esocial(self):
        """No eSocial, para CNPJ informa-se apenas a raiz (8 posições)."""
        return self.nr_insc[:8] if self.tp_insc == 1 else self.nr_insc

    @property
    def optante_simples(self):
        return self.class_trib in {"01", "02", "03", "04"}

    @property
    def recolhe_cpp_patronal(self):
        """Simples Nacional (exceto Anexo IV) não recolhe a cota patronal de 20% fora do DAS."""
        return not self.optante_simples or self.simples_anexo_iv

    @property
    def transmissor(self):
        doc = self.transmissor_cnpj or self.nr_insc
        tp = 1 if len(doc) == 14 else 2
        return tp, doc

    # --- certificado -----------------------------------------------------
    def definir_senha_certificado(self, senha: str):
        self.certificado_senha_cifrada = cifrar(senha)

    @property
    def senha_certificado(self) -> str:
        return decifrar(self.certificado_senha_cifrada)

    @property
    def tem_certificado(self):
        return bool(self.certificado) and bool(self.certificado_senha_cifrada)

    def clean(self):
        from django.core.exceptions import ValidationError

        erros = {}
        if self.tp_insc == 1 and not cnpj_valido(self.nr_insc):
            erros["nr_insc"] = "CNPJ inválido."
        if self.cnpj_sindicato and not cnpj_valido(self.cnpj_sindicato):
            erros["cnpj_sindicato"] = "CNPJ do sindicato inválido."
        if self.transmissor_cnpj and len(normalizar_cnpj(self.transmissor_cnpj)) == 14 and not cnpj_valido(
            self.transmissor_cnpj
        ):
            erros["transmissor_cnpj"] = "CNPJ do transmissor inválido."
        if len(so_digitos(self.cnae)) != 7:
            erros["cnae"] = "Informe o CNAE com 7 dígitos."
        if erros:
            raise ValidationError(erros)

    # --- aliquotas patronais --------------------------------------------
    @property
    def aliq_rat_ajustada(self) -> Decimal:
        return (Decimal(self.aliq_rat) * self.fap).quantize(Decimal("0.0001"))

    @property
    def cod_lotacao_padrao(self):
        return "LOT01"


class Acesso(models.Model):
    """Vínculo da dona (usuário que não é do escritório) com a empresa que ela pode ver no portal."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="acessos")
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="acessos")
    termos_versao = models.CharField("versão dos termos aceitos", max_length=20)
    termos_aceitos_em = models.DateTimeField(default=timezone.now)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("usuario", "empresa")]

    def __str__(self):
        return f"{self.usuario} → {self.empresa}"


class Convite(models.Model):
    """Link de uso único (7 dias) para a dona de uma empresa já cadastrada criar a conta."""

    VALIDADE = timedelta(days=7)

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="convites")
    codigo_hash = models.CharField(max_length=64, unique=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    criado_em = models.DateTimeField(default=timezone.now)
    usado_em = models.DateTimeField(null=True, blank=True)
    usado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    @staticmethod
    def _hash(codigo: str) -> str:
        return hashlib.sha256(codigo.encode()).hexdigest()

    @classmethod
    def criar(cls, empresa, por):
        """Devolve (convite, código em claro). O código só existe nesta resposta; o banco guarda o hash."""
        codigo = secrets.token_urlsafe(32)
        return cls.objects.create(empresa=empresa, criado_por=por, codigo_hash=cls._hash(codigo)), codigo

    @classmethod
    def pelo_codigo(cls, codigo: str):
        return cls.objects.filter(
            codigo_hash=cls._hash(codigo or ""), usado_em__isnull=True, criado_em__gt=timezone.now() - cls.VALIDADE
        ).select_related("empresa").first()


class Preferencia(models.Model):
    """Cor e aparência escolhidas pela pessoa; valem em qualquer navegador, mesmo depois de sair."""

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preferencia")
    cor = models.CharField(max_length=20, blank=True)
    tema = models.CharField(max_length=10, blank=True, help_text="light, dark ou vazio (automático)")

    def __str__(self):
        return f"Preferências de {self.usuario}"
