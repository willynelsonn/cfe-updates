# FolhaWeb: resumo para continuar em outra sessão

Sistema de folha de pagamento (departamento pessoal).

## Onde está o código
- **Repositório no GitHub:** `willynelsonn/cfe-updates`, branch `main`.
- **Leia primeiro:**
  - `HISTORICO.md`: histórico completo, decisões e pendências;
  - `README.md`: manual de uso.
- **No meu PC:** `C:\Users\Willyson Oliveira\Documents\cfe-updates`

## O que o sistema faz
- **Base:** Django 5.2. Usa SQLite no PC ou PostgreSQL (Supabase) na nuvem.
- **Cadastros:** empresas e funcionários, com dependentes e cargos (CBO).
- **Folha mensal:** horas extras, DSR, adicionais, faltas e vale-transporte.
- **Férias, 13º e rescisão (TRCT):** regras da CLT e tabelas de 2026 (INSS, IRRF com a Lei 15.270, FGTS).
- **eSocial S-1.3:** eventos S-1000 a S-2299, S-1200, S-1210 e S-1299.
  - O XML é validado nos XSDs oficiais, assinado e enviado por uma fila automática.
  - **Nunca foi testado no webservice real.**
- **Guias:** prévia do DARF da DCTFWeb e do FGTS Digital.
- **Gestão:** custo de cada funcionário, painel, alertas de prazos legais e 6 cores de tema (padrão Grafite).
- **20 relatórios** (menu Relatórios), todos com impressão/PDF e exportação para Excel.

## Como rodar no meu PC
- Dê dois cliques no `FolhaWeb.bat` (ou no atalho da Área de Trabalho).
- **Endereço:** `http://127.0.0.1:8000`
- **Usuário:** `willysonoliveira`

## Nuvem (pedido atual): Render + Supabase
O código está pronto:
- `render.yaml` para o Render;
- banco configurado pela variável `FOLHA_DATABASE_URL`;
- certificados digitais guardados dentro do banco;
- o sistema tranca sozinho a API pública do Supabase.

**Falta criar as contas e publicar.** O passo a passo está no README, seção "Publicar na nuvem (Render + Supabase)":

1. **Supabase**
   - Crie o projeto `folhaweb`, região **East US (North Virginia)**.
   - Use uma senha do banco só com letras e números.
   - Copie a URI do **Session pooler**.
2. **Render**
   - Vá em New + › Blueprint › `cfe-updates`.
   - Preencha:
     - `FOLHA_DATABASE_URL`
     - `DJANGO_SUPERUSER_USERNAME=willysonoliveira`
     - `DJANGO_SUPERUSER_PASSWORD`
   - Clique em **Apply**.

A extensão **Claude in Chrome** já está instalada no meu Chrome. **Eu faço só os logins e digito as senhas**; o resto pode ser feito pelo navegador.

## Alternativas prontas, mas que não estão em uso
`Servidor.bat`, `InstalarNoServidor.bat` e `ConfigurarDominio.bat` publicam o sistema a partir do próprio PC, pelo Cloudflare Tunnel.

## O que falta
1. Publicar no Render + Supabase e testar o login no endereço `onrender.com`.
2. Cadastrar a empresa real (CNPJ e certificado A1) e os funcionários, e calcular a primeira folha.
3. Testar o eSocial em **produção restrita**.
4. Pedir ao contador para confirmar as naturezas de rubrica listadas no README.

## Como trabalhar comigo
- Explique em português simples, passo a passo, com comandos prontos para colar.
- No fim de cada etapa, crie o PR e faça o merge.
