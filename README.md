# Ibratin — Gestor de Regras de Metas por Campanha

Aplicação web de página única (HTML + CSS + JS puro, sem build) para definir
regras de campanhas de vendas ("campanhas") — filtros por Canal, Segmento,
Grupo de Produto, Produto, Empresa e Vendedor, cruzados com meses de vigência
— que depois alimentam um modelo Power BI.

Deploy: `atomsail.github.io/ibratin-gestor-campanhas/` a partir deste
repositório (`github.com/atomsail/ibratin-gestor-campanhas`, branch `main`).

## Estrutura

```
gestor-campanhas.html       Aplicação principal (produção)
gestor-campanhas-dev.html   Cópia idêntica usada como ambiente de teste antes
                             de promover mudanças para gestor-campanhas.html
index.html                  Redirect estático para gestor-campanhas.html
                             (raiz do GitHub Pages)
exportar_dims_pbi.py        Lê as dimensões do Power BI Desktop (aberto) e
                             grava direto em gestor-campanhas.html
gerar_relacoes.py           Lê combinações válidas de dimensão no Power BI
                             Desktop e publica dim_relacoes.json
```

Não há bundler nem etapa de build — edite o `.html` direto e abra no
navegador (ou sirva com `python -m http.server` para testar login/sessão
sem as inconsistências de abrir via `file://`).

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

`gestor-campanhas-dev.html` e `gestor-campanhas.html` hoje têm o mesmo
conteúdo — o primeiro serve como ambiente de teste antes de promover uma
mudança para produção (basta sobrescrever `gestor-campanhas.html` com a
cópia validada).

## Como atualizar os filtros (dimensões + combinações válidas)

Os botões "Relações PBI" e "Atualizar Dados" que existiam no cabeçalho do
app foram removidos — o procedimento agora é feito direto pelos scripts
Python, no terminal:

1. Abra o Power BI Desktop com o `Comercial.pbip` carregado e aguarde o
   refresh completo dos dados.
2. Rode `python exportar_dims_pbi.py`. Ele lê as dimensões (canal, segmento,
   grupo, produto, empresa, vendedor) do modelo aberto e grava
   automaticamente dentro de `gestor-campanhas.html` (bloco `const DIM =
   {...}`), além de salvar uma cópia em `dims_ibratin.json` como conferência.
3. Ainda com o mesmo modelo aberto, rode `python gerar_relacoes.py`. Ele
   recalcula quais combinações de Canal/Segmento/Empresa/Vendedor/Grupo
   realmente existem nos dados (usadas para travar opções incompatíveis nos
   filtros) e salva em `dim_relacoes.json`.
4. Confira `git status`, revise o diff e commit + push para `main` — o
   GitHub Pages só serve o conteúdo depois do push.
5. Dê F5 na aplicação publicada para conferir que os filtros vieram
   atualizados.

**Atenção — pendência conhecida:** o app lê `dim_relacoes.json` de um bucket
público do Supabase Storage (`.../storage/v1/object/public/relacoes/`), mas
`gerar_relacoes.py` hoje ainda publica esse arquivo só no OneDrive (via N8N,
arquitetura antiga). Ou seja, o passo 3 acima **não atualiza de fato** o que
o app usa até esse script ser ajustado para subir o arquivo também no
Supabase Storage.

Se estiver testando fora do Power BI Desktop (ex: contra a cópia publicada
no GitHub Pages), ajuste `dims_ibratin.json`/`dim_relacoes.json` manualmente
e peça para alguém com acesso ao repositório aplicar/commitar a mudança —
não existe mais um caminho de importação manual dentro do próprio app.

## Rodando os scripts

Ambos exigem o Power BI Desktop aberto localmente com o `.pbip` carregado e
atualizado, mais a biblioteca ADOMD.NET instalada (os scripts detectam
sozinhos o caminho da DLL e a porta local do Analysis Services).

```bash
python exportar_dims_pbi.py   # atualiza as dimensões em gestor-campanhas.html
python gerar_relacoes.py      # atualiza dim_relacoes.json
```

Não há testes automatizados. Para validar mudanças no HTML, abra o arquivo
no navegador e exercite o fluxo alterado (login, filtros, salvar/editar
campanha, metas, publicar).
