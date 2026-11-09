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
| Automação | Admissão, férias e desligamento vão sozinhos para o eSocial ao salvar. Botão **Apurar e enviar** calcula, fecha e transmite a folha. Uma fila respeita a ordem exigida pelo governo (cada evento só sai depois que os que ele precisa foram aceitos) e acompanha os retornos sozinha |
| Empresas | Várias empresas (escritório contábil), CNPJ alfanumérico, Simples/Lucro, RAT/FAP, terceiros, certificado A1 com senha criptografada, opção "já cadastrada no eSocial por outro sistema" para migrar do Domínio |
| Funcionários | Cadastro completo para o S-2200, dependentes (IRRF e salário-família), cargos com CBO, desligamento |
| Folha mensal | Salário proporcional, horas extras 50%/100%, DSR, adicional noturno, insalubridade, periculosidade, faltas, vale-transporte, lançamentos livres |
| Férias | Programação com conferência da CLT (arts. 130, 134, 135, 137, 143 e 145), período aquisitivo sugerido, médias de variáveis, 1/3, abono pecuniário, INSS e IRRF, divisão do gozo entre meses, aviso e recibo para imprimir e S-2230 |
| 13º salário | 1ª parcela na folha do mês (natureza 5504, até 30/11), 2ª parcela com INSS e IRRF exclusivos e desconto do adiantamento (5001/9214), S-1200 e S-1299 anuais |
| Impostos 2026 | INSS progressivo, IRRF com a redução da Lei 15.270/2025, salário-família, FGTS 8% (aprendiz 2%) |
| Guias | DARF da DCTFWeb e GFD do FGTS Digital com valores estimados e vencimentos; DARF em PDF pela API Integra Contador (SERPRO), quando contratada |
| Conformidade | Painel de pendências legais com base legal: admissão fora do prazo, salário abaixo do mínimo, jornada, idade, férias vencidas e a vencer, 13º, prazos do eSocial, 5º dia útil, guias vencendo |
| eSocial | S-1000, S-1005, S-1010, S-1020, S-2200, S-2230, S-2299, S-1200, S-1210 e S-1299, validados nos XSDs oficiais, assinados e transmitidos em lotes |

## Ainda não faz (próximos passos sugeridos)

1. **Rescisão (TRCT)**: o S-2299 é enviado, mas as verbas rescisórias ainda precisam ser calculadas fora.
2. **Retificação** de folha já enviada (S-1200 com `indRetif = 2`) e exclusão de eventos (S-3000).
3. Afastamentos por doença/maternidade (S-2230 com outros motivos), alterações contratuais (S-2205/S-2206) e SST (S-2210/S-2220/S-2240).
4. Férias em dobro, férias coletivas, pensão alimentícia, consignado, horistas e intermitentes.
5. Feriados nacionais e municipais nos prazos (hoje só sábados e domingos são considerados).
6. Leitura dos totalizadores S-5001/S-5011 para conferir automaticamente com a prévia.
7. GFD do FGTS Digital emitida pelo sistema: o governo não oferece API pública; hoje o FolhaWeb calcula e leva até o portal.

## Pontos para o contador confirmar antes da produção

Pesquisei a regra vigente, mas estes itens não puderam ser conferidos no texto oficial a partir do ambiente onde o sistema foi feito:

- Rubricas de férias da NT S-1.3 04/2025: adiantamento **1015**, gozo **1016/1017** e compensação **9221**, além das incidências escolhidas para elas (`folha/models.py`, `RUBRICAS_PADRAO`).
- Abono pecuniário com natureza **1023** e incidência de IRRF **74** (isento).
- Retenção antecipada do INSS das férias com natureza **9200** (rubrica 9209), quando o gozo é em mês seguinte ao pagamento.
- A redução da Lei 15.270/2025 aplicada ao **13º** e às **férias** (`redutor_irrf_13` e `redutor_irrf_ferias` em `folha/tabelas.py`).
- O nome do serviço do Integra Contador para o DARF (`GERARGUIA31`, configurável).

Todas as rubricas podem ser editadas na tela **Rubricas**. Teste tudo primeiro em **produção restrita**.

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

Para o envio continuar mesmo com o navegador fechado, agende a fila no servidor (a cada 5 minutos):

```bash
*/5 * * * * cd /caminho/do/folhaweb && python manage.py processar_esocial
```

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

1. Cadastre a empresa e envie o certificado digital A1 (`.pfx`). Se ela já estiver no eSocial por outro sistema (por exemplo, o Domínio), marque "empresa já cadastrada no eSocial".
2. Cadastre cargos e funcionários. A admissão vai sozinha para o eSocial. Para quem já foi enviado pelo outro sistema, marque "admissão já enviada".
3. Todo mês, em **Folha do mês**, lance horas extras e faltas e clique em **Apurar e enviar**.
4. Quando o eSocial aceitar o fechamento, clique em **Gerar guias** e pague o DARF e a GFD até o dia 20.
5. Férias: **Programar férias** (o sistema bloqueia o que a CLT não permite). 13º: informe a 1ª parcela na folha de novembro e apure a 2ª parcela em **13º salário** até 20/12.
6. Resolva o que aparecer em **Pendências legais**, na tela inicial.

O ambiente padrão é a **produção restrita** (testes). Mude para **Produção** no cadastro da empresa só depois de validar.

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
- **S-1210** segue o regime de caixa: fica no mês do **pagamento**. O salário de outubro pago em 05/11
  entra no S-1210 de novembro, junto com as férias e a 1ª parcela do 13º pagas em novembro. Por isso a
  folha de um mês só fecha depois das folhas cujos pagamentos caem nele.
- **INSS das férias**: retido no recibo e acertado na folha do mês do gozo, para o líquido nunca ficar negativo.
- O TLS dos servidores do eSocial usa a cadeia ICP-Brasil. Se o servidor não a reconhecer, aponte
  `FOLHA_ESOCIAL_CA_BUNDLE` para um `.pem` com as ACs da ICP-Brasil.
- Os XSDs em `esocial/schemas/` são os publicados pelo governo, obtidos do projeto
  [nfephp-org/sped-esocial](https://github.com/nfephp-org/sped-esocial).
