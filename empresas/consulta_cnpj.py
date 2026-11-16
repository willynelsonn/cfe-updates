"""Consulta pública do CNPJ (BrasilAPI) para preencher o cadastro. Se falhar, a dona digita o nome."""

import requests

from .validators import normalizar_cnpj

URL = "https://brasilapi.com.br/api/cnpj/v1/{}"


def consultar_cnpj(cnpj: str) -> dict | None:
    try:
        r = requests.get(URL.format(normalizar_cnpj(cnpj)), timeout=5)
        if r.status_code != 200:
            return None
        d = r.json()
        cnae = str(d.get("cnae_fiscal") or "")
        return {
            "razao_social": (d.get("razao_social") or "")[:115],
            "nome_fantasia": (d.get("nome_fantasia") or "")[:115],
            "cnae": cnae.zfill(7) if cnae else "",
            "municipio": (d.get("municipio") or "")[:60],
            "uf": (d.get("uf") or "")[:2],
        }
    except Exception:  # fora do ar, resposta estranha, sem internet: a dona digita
        return None
