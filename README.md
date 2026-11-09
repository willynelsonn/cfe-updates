# FolhaWeb

Sistema web de departamento pessoal: cadastro de empresas e funcionários, cálculo
da folha mensal, holerites e envio ao **eSocial** (leiaute S-1.3). A **DCTFWeb** e
a guia do **FGTS Digital** são montadas pelo governo a partir desses eventos, e o
sistema mostra uma prévia dos valores para conferência.

> **Status: primeira versão (MVP).** O sistema calcula a folha mensal e gera, assina
> e transmite os eventos, mas ainda **não foi testado contra o webservice real do
> eSocial**. Antes de usar com dados reais: teste em **produção restrita** com o
> certificado da empresa e confira tudo com um contador.

## O que já faz

| Área | Funcionalidades |
|---|---|
| Empresas | Várias empresas (escritório contábil), CNPJ alfanumérico, Simples/Lucro, RAT/FAP, terceiros, certificado A1 com a senha guardada criptografada |
| Funcionários | Cadastro completo para o S-2200, dependentes (IRRF e salário-família), cargos com CBO, desligamento |
| Folha mensal | Salário proporcional (admissão/desligamento), horas extras 50%/100%, DSR sobre horas extras, adicional noturno, insalubridade, periculosidade, faltas, vale-transporte, lançamentos livres |
| Impostos 2026 | INSS progressivo (teto R$ 8.475,55), IRRF com desconto simplificado e **redução da Lei 15.270/2025** (isenção até R$ 5.000), salário-família, FGTS 8% (aprendiz 2%) |
| Relatórios | Holerite para impressão (individual ou em lote), memória de cálculo, totais da folha, custo da empresa, prévia da DCTFWeb e do FGTS |
| eSocial | S-1000, S-1005, S-1010, S-1020, S-2200, S-1200, S-1210, S-1299 e S-2299; validação nos XSDs oficiais; assinatura digital; envio em lotes; consulta do retorno e dos recibos |
| DCTFWeb | Opção de transmissão automática da DCTFWeb no fechamento (`transDCTFWeb`) |

## Ainda não faz (próximos passos sugeridos)

1. **Rescisão (TRCT)**: cálculo das verbas rescisórias (saldo, aviso, férias e 13º proporcionais, multa do FGTS) e envio no S-2299. Hoje o S-2299 vai sem verbas.
2. **Férias** (cálculo, aviso e recibo) e **13º salário** (1ª e 2ª parcelas, S-1200 anual).
3. **Afastamentos** (S-2230), **alterações contratuais** (S-2205/S-2206) e **SST** (S-2210/S-2220/S-2240).
4. Pensão alimentícia, consignado (eConsignado), horistas, intermitentes, várias lotações/estabelecimentos.
5. Leitura dos totalizadores do eSocial (S-5001, S-5002, S-5003, S-5011, S-5013) para conferir automaticamente com a prévia.
6. Emissão do DARF da DCTFWeb por API (Integra Contador do SERPRO, serviço pago).
7. Importação de funcionários de outro sistema (por exemplo, do Domínio) via planilha.

## Como rodar

Requisitos: Python 3.11+.

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

```bash
python manage.py migrate
```

Para conhecer o sistema com uma empresa fictícia (cria o usuário `admin` com senha `admin`):

```bash
python manage.py dados_demo
```

Ou crie seu próprio usuário:

```bash
python manage.py createsuperuser
```

```bash
python manage.py runserver
```

Acesse http://127.0.0.1:8000.

Testes automáticos:

```bash
python manage.py test
```

### Produção

Use as variáveis de `.env.example` (chave secreta, PostgreSQL, domínio, pasta privada para
os certificados) e rode atrás de um servidor HTTPS (por exemplo, gunicorn + nginx).
**Faça backup do banco e da pasta de certificados**: a senha do certificado é cifrada com
a `FOLHA_SECRET_KEY`. Se ela mudar, será preciso reenviar o certificado.

## Roteiro de uso

1. Cadastre a empresa e envie o certificado digital A1 (`.pfx`).
2. Em **eSocial**, gere os eventos iniciais (S-1000, S-1005, S-1010, S-1020) e transmita. Isso se faz uma vez por empresa.
3. Cadastre cargos e funcionários. Na ficha de cada um, gere o **S-2200** (até o dia anterior ao início do trabalho).
4. Em **Competências**, abra o mês, lance horas extras, faltas etc. e clique em **Calcular folha**.
5. Confira holerites e totais e clique em **Fechar** para gerar S-1200, S-1210 e S-1299.
6. Em **eSocial**, clique em **Transmitir pendentes** e, alguns minutos depois, em **Consultar retorno**.
7. Emita o DARF na DCTFWeb (e-CAC) e a guia no FGTS Digital (veja a tela "DCTFWeb e FGTS").

Comece com o ambiente **Produção restrita** (o padrão). Mude para **Produção** no cadastro da
empresa só depois de validar.

## Estrutura

```
config/      configurações, URLs e painel inicial
empresas/    empregadores, certificado digital, validação de CPF/CNPJ
pessoal/     funcionários, dependentes e cargos
folha/       rubricas, competências, motor de cálculo (calculo.py), tabelas legais (tabelas.py)
esocial/     geração dos XMLs, assinatura, validação XSD, webservice SOAP, lotes
  schemas/   XSDs oficiais do eSocial S-1.3 e do lote de envio
templates/   telas (HTML)
```

## Manutenção anual das tabelas

As faixas de INSS, IRRF, salário mínimo e salário-família ficam em `folha/tabelas.py`. Todo
começo de ano é preciso incluir a tabela nova. Se faltar a tabela do ano, o sistema usa a
mais recente e mostra um aviso na tela da competência. Valores de 2026 usados:

- Salário mínimo R$ 1.621,00 (Decreto 12.797/2025).
- INSS: 7,5% até 1.621,00; 9% até 2.902,84; 12% até 4.354,27; 14% até 8.475,55 (Portaria Interministerial MPS/MF 13/2026).
- IRRF: tabela vigente desde 05/2025 (isento até 2.428,80; desconto simplificado 607,20; dependente 189,59) com a redução mensal da Lei 15.270/2025 (até R$ 312,89 para rendimentos até R$ 5.000; `978,62 − 0,133145 × rendimento` entre R$ 5.000,01 e R$ 7.350).
- Salário-família: R$ 67,54 por filho, para remuneração até R$ 1.980,38.

Confira esses números na fonte oficial antes de usar. A redução do IRRF é calculada sobre o
rendimento tributável bruto do mês.

## Notas técnicas

- **Assinatura digital**: XMLDSig envelopada (`Reference URI=""`), RSA-SHA256, C14N inclusiva e
  `<Signature>` sem prefixo, como o eSocial exige. O algoritmo foi implementado direto em
  `esocial/assinatura.py` porque o libxml2 2.14 gera `xmlns=""` indevido ao canonicalizar o
  `<SignedInfo>`, o que invalidaria a assinatura. Os testes conferem a assinatura com um
  verificador independente, baseado na biblioteca padrão do Python.
- **S-1210** fica no período do **pagamento**, e não no da competência: o salário de outubro pago
  em 05/11 gera S-1210 em 2026-11. O S-1299 de outubro sai com `evtPgtos = N`.
- O TLS dos servidores do eSocial usa a cadeia ICP-Brasil. Se o servidor não a reconhecer, aponte
  `FOLHA_ESOCIAL_CA_BUNDLE` para um `.pem` com as ACs da ICP-Brasil.
- Os XSDs em `esocial/schemas/` são os publicados pelo governo, obtidos do projeto
  [nfephp-org/sped-esocial](https://github.com/nfephp-org/sped-esocial).
