"""Exporta e importa funcionários em planilha (.xlsx ou CSV) para trocar dados com o Domínio e com o Excel.

As colunas são os campos de ``Funcionario``, com o nome que aparece nas telas. O CPF identifica a pessoa:
se já existe na empresa, a linha atualiza; se não existe, cria. Célula vazia não apaga dado.
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from itertools import islice

from django.db import models, transaction
from django.forms.models import model_to_dict
from django.utils.text import capfirst
from openpyxl import Workbook, load_workbook

from empresas.validators import formatar_cpf, so_digitos

from .forms import FuncionarioForm
from .models import Cargo, Funcionario

CAMPOS = {
    f.name: f for f in Funcionario._meta.fields if f.name not in ("id", "empresa", "criado_em", "atualizado_em")
}
CABECALHOS = {nome: capfirst(f.verbose_name) for nome, f in CAMPOS.items()}
MAX_LINHAS = 5000
MAX_COLUNAS = 100


class ErroPlanilha(Exception):
    pass


class FuncionarioImportForm(FuncionarioForm):
    class Meta(FuncionarioForm.Meta):
        exclude = ["empresa"]


@dataclass
class Linha:
    numero: int
    nome: str
    cpf: str
    acao: str = "criar"  # criar | atualizar | igual
    mudancas: list = field(default_factory=list)
    erros: list = field(default_factory=list)
    form: FuncionarioImportForm | None = None


# ---------- Exportar ----------

FORMULA = ("=", "+", "-", "@")


def _valor(func, campo):
    v = getattr(func, campo)
    if campo == "cpf":
        return formatar_cpf(v)  # com pontos, o Excel não come o zero da frente
    if campo == "cargo":
        v = v.nome
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    if isinstance(v, str) and len(v) > 1 and v.startswith(FORMULA):
        return "'" + v  # o Excel não executa como fórmula; a importação tira o apóstrofo
    return v


def exportar(empresa, formato="xlsx") -> bytes:
    funcs = Funcionario.objects.filter(empresa=empresa).select_related("cargo").order_by("nome")
    linhas = [[_valor(f, c) for c in CAMPOS] for f in funcs]
    if formato == "csv":
        saida = io.StringIO()
        escritor = csv.writer(saida, delimiter=";")  # ";" é o que o Excel em português abre direto
        escritor.writerow(CABECALHOS.values())
        for linha in linhas:
            escritor.writerow([
                v.strftime("%d/%m/%Y") if isinstance(v, date)
                else str(v).replace(".", ",") if isinstance(v, Decimal)
                else "" if v is None else v
                for v in linha
            ])
        return saida.getvalue().encode("utf-8-sig")
    wb = Workbook()
    ws = wb.active
    ws.title = "Funcionários"
    ws.append(list(CABECALHOS.values()))
    for linha in linhas:
        ws.append(linha)
    for coluna in ws.iter_cols(min_row=2):
        for celula in coluna:
            if isinstance(celula.value, (date, datetime)):
                celula.number_format = "DD/MM/YYYY"
    saida = io.BytesIO()
    wb.save(saida)
    return saida.getvalue()


# ---------- Importar ----------

def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    t = str(v).strip()
    return t[1:] if t[:1] == "'" and t[1:2] in FORMULA and len(t) > 2 else t


def _chave(v) -> str:
    """Compara textos sem acento, maiúsculas, espaços ou pontuação: "Data de admissão" == "data_de_admissao"."""
    t = unicodedata.normalize("NFKD", _texto(v)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t)


def _ler(conteudo: bytes, nome_arquivo: str) -> list[list]:
    if nome_arquivo.lower().endswith(".xlsx"):
        try:
            wb = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
            linhas = [list(r) for r in islice(wb.worksheets[0].iter_rows(values_only=True, max_col=MAX_COLUNAS), MAX_LINHAS + 2)]
            wb.close()
            return linhas
        except Exception as exc:  # arquivo corrompido ou que não é .xlsx de verdade
            raise ErroPlanilha("Não consegui abrir a planilha. Salve como .xlsx ou .csv e envie de novo.") from exc
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("cp1252", errors="replace")  # CSV salvo pelo Excel no Windows
    cabecalho = texto.split("\n", 1)[0]
    separador = max(";\t|,", key=cabecalho.count)  # o que mais aparece no cabeçalho; empate fica com ";"
    return list(islice(csv.reader(io.StringIO(texto), delimiter=separador), MAX_LINHAS + 2))


def _converter(campo: str, v, cargos: dict):
    f = CAMPOS[campo]
    if campo == "cargo":
        cargo = cargos.get(_chave(v))
        if cargo is None:
            raise ValueError(f"o cargo “{_texto(v)}” não existe nesta empresa (cadastre em Cargos).")
        return cargo.pk
    if campo in ("cpf", "cep"):
        # O Excel tira o zero da frente de números; o CPF ainda passa pela conta dos dígitos depois.
        digitos = so_digitos(_texto(v))
        return digitos.zfill(11 if campo == "cpf" else 8) if digitos else ""
    if campo == "telefone":
        return so_digitos(_texto(v))
    if isinstance(f, models.BooleanField):
        t = _chave(v)
        if t in ("sim", "s", "1", "true", "verdadeiro", "x"):
            return True
        if t in ("nao", "n", "0", "false", "falso"):
            return False
        raise ValueError("use Sim ou Não.")
    if isinstance(f, models.DateField):
        return v.date() if isinstance(v, datetime) else v if isinstance(v, date) else _texto(v)
    if isinstance(f, models.DecimalField):
        if isinstance(v, (int, float)):
            return round(Decimal(str(v)), f.decimal_places)
        t = _texto(v).replace("R$", "").strip()
        return t.replace(".", "").replace(",", ".") if "," in t else t
    if f.choices:
        # Aceita o código (com ou sem zero na frente) ou o nome da opção: "07", "7" ou "Ensino médio completo".
        t = _chave(v)
        for codigo, rotulo in f.choices:
            if t.lstrip("0") == _chave(codigo).lstrip("0") or t == _chave(rotulo):
                return codigo
    return _texto(v)


def analisar(conteudo: bytes, nome_arquivo: str, empresa, ja_no_esocial=False):
    """Lê a planilha e valida cada linha, sem gravar nada. Devolve (linhas, colunas ignoradas)."""
    linhas = [r for r in _ler(conteudo, nome_arquivo) if any(_texto(v) for v in r)]
    if len(linhas) < 2:
        raise ErroPlanilha("A planilha está vazia: precisa do cabeçalho e de ao menos um funcionário.")
    if len(linhas) > MAX_LINHAS + 1:
        raise ErroPlanilha(f"São no máximo {MAX_LINHAS} funcionários por arquivo.")
    por_chave = {}
    for nome, f in CAMPOS.items():
        por_chave[_chave(nome)] = por_chave[_chave(f.verbose_name)] = nome
    colunas = [por_chave.get(_chave(c)) for c in linhas[0]]
    if "cpf" not in colunas:
        raise ErroPlanilha("A planilha precisa ter uma coluna “CPF”.")
    ignoradas = [_texto(c) for c, campo in zip(linhas[0], colunas) if _texto(c) and not campo]

    cargos = {_chave(c.nome): c for c in Cargo.objects.filter(empresa=empresa)}
    existentes = {f.cpf: f for f in Funcionario.objects.filter(empresa=empresa)}
    vistos_cpf, vistas_matriculas, resultado = {}, {}, []
    for numero, valores in enumerate(linhas[1:], start=2):
        celulas = {campo: v for campo, v in zip(colunas, valores) if campo and _texto(v)}
        linha = Linha(numero, _texto(celulas.get("nome")), formatar_cpf(_converter("cpf", celulas.get("cpf"), cargos)))
        resultado.append(linha)
        dados, com_erro = {}, set()
        for campo, v in celulas.items():
            try:
                dados[campo] = _converter(campo, v, cargos)
            except ValueError as exc:
                linha.erros.append(f"{CABECALHOS[campo]}: {exc}")
                com_erro.add(campo)
        func = existentes.get(dados.get("cpf"))
        if func is None:
            func = Funcionario(empresa=empresa, esocial_ja_cadastrado=ja_no_esocial)
        else:
            linha.acao = "atualizar"
        base = model_to_dict(func, fields=list(CAMPOS))
        form = FuncionarioImportForm({**base, **dados}, instance=func, empresa=empresa)
        if form.is_valid():
            linha.form = form
            if func.pk and not form.has_changed():
                linha.acao = "igual"
            linha.mudancas = [CABECALHOS[c] for c in form.changed_data] if func.pk else []
        else:
            linha.erros += [
                f"{CABECALHOS.get(c, 'Linha')}: {' '.join(msgs)}" for c, msgs in form.errors.items() if c not in com_erro
            ]
        for aviso, valor, vistos in (("CPF repetido", dados.get("cpf"), vistos_cpf),
                                     ("Matrícula repetida", _texto(form.data.get("matricula")), vistas_matriculas)):
            if valor and valor in vistos:
                linha.erros.append(f"{aviso} na planilha (já está na linha {vistos[valor]}).")
            vistos.setdefault(valor, numero)
    return resultado, ignoradas


def gravar(linhas: list[Linha]) -> tuple[int, int]:
    """Grava tudo de uma vez (ou nada). Não manda nada ao eSocial: isso só acontece pelas telas de admissão."""
    with transaction.atomic():
        for linha in linhas:
            if linha.acao != "igual":
                linha.form.save()
    return sum(l.acao == "criar" for l in linhas), sum(l.acao == "atualizar" for l in linhas)
