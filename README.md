# Ibratin — Gestor de Regras de Metas por Campanha

Aplicação web de página única (HTML + CSS + JS puro, sem build) para definir
regras de campanhas de vendas ("campanhas") — filtros por Canal, Segmento,
Grupo de Produto, Produto, Empresa e Vendedor, cruzados com meses de vigência
— e Metas Corporativas — metas por uma única dimensão (ex: faturamento por
vendedor no ano), independentes de campanha — que depois alimentam um modelo
Power BI.

Deploy: `atomsail.github.io/ibratin-gestor-campanhas/` a partir deste
repositório (`github.com/atomsail/ibratin-gestor-campanhas`, branch `main`).

## Estrutura

```
index.html                  Redirect estático para gestor-campanhas.html
                             (raiz do GitHub Pages — não mover)
gestor-campanhas.html       Aplicação principal (produção, raiz — não mover)
config.js                   SUPABASE_URL e SUPABASE_ANON_KEY (ver "Credenciais" abaixo)

dev/
  gestor-campanhas-dev.html Cópia idêntica usada como ambiente de teste antes
                             de promover mudanças para gestor-campanhas.html

scripts/
  exportar_dims_pbi.py      Lê as dimensões do Power BI Desktop (aberto) e
                             grava direto em ../gestor-campanhas.html
  gerar_relacoes.py         Lê combinações válidas de dimensão no Power BI
                             Desktop e publica dim_relacoes.json [LEGADO, ver abaixo]
  config.ini                Credenciais usadas pelos scripts (git-ignored)
  config.ini.example        Template do config.ini, sem segredo real

sql/
  supabase_metas_corporativas.sql
                             DDL das tabelas de Metas Corporativas — roda
                             manualmente no SQL Editor do Supabase, não é
                             executado automaticamente por nada neste repo
```

Não há bundler nem etapa de build — edite o `.html` direto e abra no
navegador (ou sirva com `python -m http.server` para testar login/sessão
sem as inconsistências de abrir via `file://`).

## Credenciais

- **Supabase URL + anon key** — em `config.js`, carregado antes do script
  principal em `gestor-campanhas.html`/`dev/gestor-campanhas-dev.html`. É a
  chave **anon**, pública por design e protegida por RLS no banco — como é um
  site estático sem backend, ela necessariamente chega ao navegador de algum
  jeito; `config.js` só existe para isolar isso da lógica do app, não para
  "escondê-la" (não dá pra esconder de verdade sem um backend).
- **Webhook N8N** (`gerar_relacoes.py`, fluxo legado — ver seção abaixo) —
  em `scripts/config.ini` (git-ignored). Copie `scripts/config.ini.example`
  para `scripts/config.ini` e preencha `[n8n] write_url` antes de rodar o
  script.

## Arquitetura

O backend é **Supabase**: autenticação (login/cadastro com aprovação de
admin), e três tabelas — `campanhas` (regra + filtros, em JSON), `metas`
(meta numérica por vendedor × mês × campanha) e `regras_expandidas` (a regra
já "explodida" linha a linha, é o que o Dataflow do Power BI consome via
PostgREST). O botão **"☁️ Publicar"** dentro do app grava `campanhas` e
reconstrói `regras_expandidas` inteira a partir dela — é a única forma
confiável de gerar essa tabela, porque reaproveita a mesma lógica de
expansão de filtros já testada no app (nunca reimplementar essa lógica em
outra linguagem).

`dev/gestor-campanhas-dev.html` e `gestor-campanhas.html` hoje têm o mesmo
conteúdo — o primeiro serve como ambiente de teste antes de promover uma
mudança para produção (basta sobrescrever `gestor-campanhas.html` com a
cópia validada).

### Metas Corporativas

Segunda aba do app ("🎯 Metas Corporativas"), para metas que variam numa
única dimensão (canal, segmento, grupo, produto, empresa ou vendedor) — ex:
"faturamento por vendedor em 2026" — sem estar amarrada a uma campanha.
Segue o mesmo padrão de CRUD/edição/duplicação/exclusão e o mesmo fluxo de
"salvar local → sincronizar Supabase" das campanhas.

Backend em três tabelas próprias (DDL em `supabase_metas_corporativas.sql`,
rode manualmente no SQL Editor do Supabase):

- `metas_corporativas` — definição da meta (nome, ano, agrupamento, filtro).
- `metas_corporativas_valores` — valor por item resolvido × mês.
- `metas_corporativas_expandidas` — grão item×mês que o Dataflow do Power BI
  lê via PostgREST; reconstruída do zero pelo botão **"☁️ Publicar"** dessa
  aba, no mesmo padrão de `regras_expandidas`.

## Como atualizar os filtros (dimensões + combinações válidas)

Os botões "Relações PBI" e "Atualizar Dados" que existiam no cabeçalho do
app foram removidos — o procedimento agora é feito direto pelos scripts
Python, no terminal:

1. Abra o Power BI Desktop com o `Comercial.pbip` carregado e aguarde o
   refresh completo dos dados.
2. Rode `python scripts/exportar_dims_pbi.py`. Ele lê as dimensões (canal,
   segmento, grupo, produto, empresa, vendedor) do modelo aberto e grava
   automaticamente dentro de `gestor-campanhas.html` (bloco `const DIM =
   {...}`), além de salvar uma cópia em `scripts/dims_ibratin.json` como
   conferência.
3. Ainda com o mesmo modelo aberto, rode `python scripts/gerar_relacoes.py`
   (fluxo legado, ver aviso abaixo).
4. Confira `git status`, revise o diff e commit + push para `main` — o
   GitHub Pages só serve o conteúdo depois do push.
5. Dê F5 na aplicação publicada para conferir que os filtros vieram
   atualizados.

**Atenção — pendência conhecida:** `gerar_relacoes.py` é de uma arquitetura
antiga — ele publica `dim_relacoes.json` no OneDrive via um webhook N8N, mas
o app atual lê esse arquivo de um bucket público do Supabase Storage
(`.../storage/v1/object/public/relacoes/dim_relacoes.json`). Esse bucket
**ainda não existe** (confirmado em 2026-10-17 — a URL retorna "Bucket not
found"), então o passo 3 acima não atualiza de fato o que o app usa, e o
cross-filter de relações está efetivamente inoperante em produção. A versão
atual do projeto não usa mais N8N/OneDrive para nada além disso — o conserto
real é reescrever `gerar_relacoes.py` para publicar direto no Supabase
Storage, ainda não feito.

Se estiver testando fora do Power BI Desktop (ex: contra a cópia publicada
no GitHub Pages), ajuste `dims_ibratin.json`/`dim_relacoes.json` manualmente
e peça para alguém com acesso ao repositório aplicar/commitar a mudança —
não existe mais um caminho de importação manual dentro do próprio app.

## Rodando os scripts

Ambos exigem o Power BI Desktop aberto localmente com o `.pbip` carregado e
atualizado, mais a biblioteca ADOMD.NET instalada (os scripts detectam
sozinhos o caminho da DLL e a porta local do Analysis Services).

```bash
python scripts/exportar_dims_pbi.py   # atualiza as dimensões em gestor-campanhas.html
python scripts/gerar_relacoes.py      # [legado] atualiza dim_relacoes.json, publica via N8N
```

Não há testes automatizados. Para validar mudanças no HTML, abra o arquivo
no navegador e exercite o fluxo alterado (login, filtros, salvar/editar
campanha, metas, publicar).
