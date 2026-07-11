"""
exportar_dims_pbi.py
====================
Conecta ao Analysis Services local do Power BI Desktop (quando aberto com
Comercial.pbip), extrai as dimensoes via DAX e salva dims_ibratin.json.

Como usar:
    1. Abra o Comercial.pbip no Power BI Desktop
    2. Aguarde o carregamento completo dos dados
    3. Execute: python exportar_dims_pbi.py
    4. Recarregue gestor-campanhas.html no navegador (F5)

O script atualiza gestor-campanhas.html automaticamente e tambem
salva dims_ibratin.json como backup. O botao "Atualizar Dados"
no HTML pode ser usado como alternativa (importa o JSON manualmente).

Sem dependencias extras alem de Python 3.8+.
"""

import os, re, json, sys, glob, subprocess, tempfile

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
OUTPUT_JSON = os.path.join(SCRIPT_DIR, "dims_ibratin.json")
HTML_PATH   = os.path.join(SCRIPT_DIR, "gestor-campanhas.html")

# ADOMD.NET DLL — detectada na maquina
ADOMD_CANDIDATES = [
    r"C:\Program Files\Microsoft.NET\ADOMD.NET\160\Microsoft.AnalysisServices.AdomdClient.dll",
    r"C:\Program Files\Microsoft.NET\ADOMD.NET\150\Microsoft.AnalysisServices.AdomdClient.dll",
    r"C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.AdomdClient.dll",
    r"C:\Program Files (x86)\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.AdomdClient.dll",
    r"C:\Program Files\On-premises data gateway\Microsoft.AnalysisServices.AdomdClient.dll",
]

# ─────────────────────────────────────────────
#  LOCALIZAR PORTA DO AS LOCAL
# ─────────────────────────────────────────────

def encontrar_porta() -> str | None:
    """Busca o arquivo msmdsrv.port.txt em todos os workspaces conhecidos."""
    localappdata = os.environ.get("LOCALAPPDATA", "")
    userprofile  = os.environ.get("USERPROFILE", "")

    raizes = [
        # Versao desktop classica
        os.path.join(localappdata, "Microsoft", "Power BI Desktop", "AnalysisServicesWorkspaces"),
        # Versao Store App (caminho diferente — nao usa LOCALAPPDATA)
        os.path.join(userprofile, "Microsoft", "Power BI Desktop Store App", "AnalysisServicesWorkspaces"),
        # Alternativas Store em LOCALAPPDATA/Packages
        *[
            os.path.join(localappdata, "Packages", pkg, "LocalState", "AnalysisServicesWorkspaces")
            for pkg in (os.listdir(os.path.join(localappdata, "Packages")) if os.path.isdir(os.path.join(localappdata, "Packages")) else [])
            if "MicrosoftPowerBIDesktop" in pkg
        ],
    ]

    port_files = []
    for raiz in raizes:
        pattern = os.path.join(raiz, "*", "Data", "msmdsrv.port.txt")
        port_files.extend(glob.glob(pattern))

    if not port_files:
        return _porta_via_processo()

    # Mais recente primeiro
    port_files.sort(key=os.path.getmtime, reverse=True)
    return _ler_porta(port_files[0])


def _ler_porta(path: str) -> str | None:
    """Le msmdsrv.port.txt — suporta UTF-8, UTF-16 LE sem BOM e qualquer variante."""
    import re as _re
    with open(path, "rb") as f:
        raw = f.read()
    # Extrai apenas digitos do conteudo binario (funciona com qualquer encoding)
    digitos = b"".join(_re.findall(rb"\d", raw)).decode("ascii")
    return digitos if digitos else None


def _porta_via_processo() -> str | None:
    """Tenta extrair a porta do processo msmdsrv.exe via WMI."""
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='msmdsrv.exe'", "get", "commandline", "/format:list"],
            capture_output=True, text=True, timeout=10
        )
        for line in r.stdout.splitlines():
            if "-port" in line.lower():
                parts = line.split()
                for i, p in enumerate(parts):
                    if p.lower() in ("-port", "/port") and i + 1 < len(parts):
                        return parts[i + 1]
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────
#  LOCALIZAR ADOMD.NET DLL
# ─────────────────────────────────────────────

def encontrar_adomd() -> str | None:
    for path in ADOMD_CANDIDATES:
        if os.path.isfile(path):
            return path
    # Busca mais ampla
    for base in [r"C:\Program Files", r"C:\Program Files (x86)"]:
        hits = glob.glob(os.path.join(base, "**", "Microsoft.AnalysisServices.AdomdClient.dll"), recursive=True)
        if hits:
            return hits[0]
    return None


# ─────────────────────────────────────────────
#  QUERY VIA POWERSHELL + ADOMD.NET
# ─────────────────────────────────────────────

PS_TEMPLATE = r"""
param([string]$Port, [string]$AdomdDll, [string]$OutFile)
$ErrorActionPreference = 'Stop'

Add-Type -Path $AdomdDll

$connStr = "Data Source=localhost:$Port;Timeout=120"
$conn    = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection($connStr)
$conn.Open()

function RunDAX([string]$Dax) {
    $cmd = $conn.CreateCommand()
    $cmd.CommandText = $Dax
    $reader = $cmd.ExecuteReader()
    $n = $reader.FieldCount
    $cols = @(); for ($i=0;$i -lt $n;$i++){$cols += $reader.GetName($i)}
    $rows = [System.Collections.Generic.List[object]]::new()
    while ($reader.Read()) {
        $row = [ordered]@{}
        for ($i=0;$i -lt $n;$i++){
            $v = $reader.GetValue($i)
            $row[$cols[$i]] = if ($null -eq $v) {''} else {"$v".Trim()}
        }
        $rows.Add([pscustomobject]$row)
    }
    $reader.Close()
    return ,$rows
}

function TentarDAX([string]$Dax) {
    try { return RunDAX($Dax) } catch { return @() }
}

$result = [ordered]@{
    canal    = RunDAX('EVALUATE DISTINCT(SELECTCOLUMNS(fFaturamento,"CANAL",fFaturamento[CANAL])) ORDER BY [CANAL]')
    segmento = RunDAX('EVALUATE DISTINCT(SELECTCOLUMNS(fFaturamento,"SEGMENTO",fFaturamento[SEGMENTO])) ORDER BY [SEGMENTO]')
    grupo    = RunDAX('EVALUATE SUMMARIZE(dProdutos, dProdutos[Grupo Produto])')
    produto  = RunDAX('EVALUATE SUMMARIZE(dProdutos, dProdutos[Produto], dProdutos[DESCRICAO], dProdutos[Grupo Produto])')
    empresa  = TentarDAX('EVALUATE DISTINCT(SELECTCOLUMNS(fFaturamento,"EMPRESA",fFaturamento[EMPRESA])) ORDER BY [EMPRESA]')
    vendedor = TentarDAX('EVALUATE DISTINCT(SELECTCOLUMNS(fFaturamento,"VENDEDOR",fFaturamento[VENDEDOR])) ORDER BY [VENDEDOR]')
}

$conn.Close()
$result | ConvertTo-Json -Depth 5 | Set-Content -Path $OutFile -Encoding UTF8
Write-Host "OK"
"""


def executar_query(porta: str, adomd: str) -> dict:
    ps_file  = os.path.join(tempfile.gettempdir(), "_pbi_query.ps1")
    raw_json = os.path.join(tempfile.gettempdir(), "_pbi_raw.json")

    with open(ps_file, "w", encoding="utf-8") as f:
        f.write(PS_TEMPLATE)

    result = subprocess.run(
        [
            "powershell", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", ps_file,
            "-Port", porta,
            "-AdomdDll", adomd,
            "-OutFile", raw_json,
        ],
        capture_output=True, text=True, encoding="utf-8", timeout=120
    )

    if result.returncode != 0 or "Error" in result.stderr:
        raise RuntimeError(result.stderr.strip() or "PowerShell falhou sem mensagem")

    if not os.path.isfile(raw_json):
        raise RuntimeError("Arquivo JSON nao gerado pelo PowerShell")

    with open(raw_json, encoding="utf-8-sig") as f:
        return json.load(f)


# ─────────────────────────────────────────────
#  PROCESSAR E SALVAR JSON
# ─────────────────────────────────────────────

def _primeiro_valor(row: dict) -> str:
    """Pega o primeiro valor não-vazio de um dict (ignora a chave)."""
    for v in row.values():
        if v:
            return str(v).strip()
    return ""


def _extrair_col(chave: str) -> str:
    """'Tabela[Col]' -> 'Col', ou retorna a chave inteira."""
    return chave.split("[")[-1].rstrip("]") if "[" in chave else chave


def _valor_por_col(row: dict, *parciais) -> str:
    """
    Busca valor pela coluna exata primeiro (sem prefixo de tabela),
    depois por match parcial. Evita que 'Produto' case com 'Grupo Produto'.
    """
    for parcial in parciais:
        p = parcial.lower()
        # 1. match exato no nome da coluna (sem prefixo de tabela)
        for k, v in row.items():
            if _extrair_col(k).lower() == p:
                return str(v).strip() if v else ""
    for parcial in parciais:
        p = parcial.lower()
        # 2. fallback: match parcial
        for k, v in row.items():
            if p in k.lower():
                return str(v).strip() if v else ""
    return ""


def processar_dims(raw: dict) -> dict:
    """
    Converte o raw do PowerShell no formato esperado pelo HTML.
    Suporta chaves com prefixo de tabela ("dProdutos[col]") ou alias simples ("col").
    """
    def simples(rows, *campos):
        result = []
        for i, r in enumerate(rows or [], 1):
            nome = _valor_por_col(r, *campos) or _primeiro_valor(r)
            if nome:
                result.append({"cd": str(i), "nome": nome})
        return result

    canal    = simples(raw.get("canal"),    "CANAL")
    segmento = simples(raw.get("segmento"), "SEGMENTO")
    empresa  = simples(raw.get("empresa"),  "EMPRESA")
    vendedor = simples(raw.get("vendedor"), "VENDEDOR")

    grupo = []
    for i, r in enumerate(raw.get("grupo") or [], 1):
        nome = _valor_por_col(r, "Grupo Produto") or _primeiro_valor(r)
        if nome:
            grupo.append({"cd": i, "nome": nome})
    grupo.sort(key=lambda g: g["nome"])
    # reindexar após sort
    for i, g in enumerate(grupo, 1):
        g["cd"] = i

    grupo_map = {g["nome"]: g["cd"] for g in grupo}

    produto = []
    for r in (raw.get("produto") or []):
        cd    = _valor_por_col(r, "Produto")       # codigo / identificador
        nome  = _valor_por_col(r, "DESCRICAO")     # descricao completa
        g_nom = _valor_por_col(r, "Grupo Produto")
        if cd:
            produto.append({"cd": cd, "nome": nome or cd, "grupo": grupo_map.get(g_nom, 0)})

    produto.sort(key=lambda p: (p["grupo"], p["nome"]))

    return {"canal": canal, "segmento": segmento, "grupo": grupo, "produto": produto,
            "empresa": empresa, "vendedor": vendedor}


# ─────────────────────────────────────────────
#  PATCH DO HTML
# ─────────────────────────────────────────────

def _escape_js(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")


def _gerar_dim_js(dims: dict) -> str:
    canal    = dims["canal"]
    segmento = dims["segmento"]
    grupo    = dims["grupo"]
    produto  = dims["produto"]
    empresa  = dims.get("empresa",  [])
    vendedor = dims.get("vendedor", [])

    def lista_simples(items):
        if not items:
            return "[]"
        linhas = [f"    {{ cd:'{_escape_js(it['cd'])}', nome:'{_escape_js(it['nome'])}' }}" for it in items]
        return "[\n" + ",\n".join(linhas) + "\n  ]"

    def lista_grupo(items):
        if not items:
            return "[]"
        linhas = [f"    {{ cd:{it['cd']}, nome:'{_escape_js(it['nome'])}' }}" for it in items]
        return "[\n" + ",\n".join(linhas) + "\n  ]"

    def lista_produto(items):
        if not items:
            return "[]"
        linhas = [f"    {{ cd:'{_escape_js(it['cd'])}', nome:'{_escape_js(it['nome'])}', grupo:{it['grupo']} }}" for it in items]
        return "[\n" + ",\n".join(linhas) + "\n  ]"

    emp_info = f"{len(empresa)} empresas" if empresa else "empresa: sem dados (campo nao encontrado em fFaturamento[EMPRESA])"
    vnd_info = f"{len(vendedor)} vendedores" if vendedor else "vendedor: sem dados (campo nao encontrado em fFaturamento[VENDEDOR])"

    return (
        "// ════════════════════════════\n"
        "//  DIMENSOES — gerado por exportar_dims_pbi.py\n"
        f"//  Fonte: Power BI Desktop (AS local)\n"
        f"//  ({len(canal)} canais, {len(segmento)} segmentos, {len(grupo)} grupos, {len(produto)} produtos)\n"
        f"//  ({emp_info}, {vnd_info})\n"
        "// ════════════════════════════\n"
        "const DIM = {\n"
        f"  canal:    {lista_simples(canal)},\n"
        f"  segmento: {lista_simples(segmento)},\n"
        f"  grupo:    {lista_grupo(grupo)},\n"
        f"  produto:  {lista_produto(produto)},\n"
        f"  empresa:  {lista_simples(empresa)},\n"
        f"  vendedor: {lista_simples(vendedor)},\n"
        "};"
    )


_REGEX_DIM = re.compile(
    r"// ═+\s*\n\s*//\s*DIMEN[\s\S]*?const DIM\s*=\s*\{[\s\S]*?\};",
    re.DOTALL,
)
_REGEX_DIM_FALLBACK = re.compile(
    r"const DIM\s*=\s*\{[\s\S]*?\};",
    re.DOTALL,
)


def patch_html(dims: dict) -> bool:
    """Substitui o bloco const DIM no HTML com os dados frescos."""
    if not os.path.isfile(HTML_PATH):
        print(f"  [AVISO] HTML nao encontrado: {HTML_PATH}")
        print("          So o JSON foi gerado. Importe-o manualmente no navegador.")
        return False

    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    dim_js = _gerar_dim_js(dims)

    novo, n = _REGEX_DIM.subn(dim_js, html)
    if n == 0:
        novo, n = _REGEX_DIM_FALLBACK.subn(dim_js, html)

    if n == 0:
        print("  [AVISO] Bloco DIM nao localizado no HTML.")
        fallback = os.path.join(SCRIPT_DIR, "_dim_gerado.js")
        with open(fallback, "w", encoding="utf-8") as f:
            f.write(dim_js)
        print(f"  Bloco JS salvo em: {fallback}")
        return False

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(novo)
    return True


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Exportar Dimensoes — Power BI Desktop (AS local)")
    print("  Ibratin Tintas e Texturas")
    print("=" * 60)

    # 1. Localizar ADOMD.NET
    print("\n[1/5] Localizando ADOMD.NET...")
    adomd = encontrar_adomd()
    if not adomd:
        print("  [ERRO] ADOMD.NET nao encontrado.")
        print("         Instale o Microsoft Analysis Services Client Library:")
        print("         https://learn.microsoft.com/pt-br/analysis-services/client-libraries")
        sys.exit(1)
    print(f"  OK: {adomd}")

    # 2. Localizar porta AS
    print("\n[2/5] Localizando Power BI Desktop (porta AS local)...")
    porta = encontrar_porta()
    if not porta:
        print("  [ERRO] Porta do AS nao encontrada.")
        print("")
        print("  Certifique-se de que:")
        print("    1. O Power BI Desktop esta ABERTO")
        print("    2. O arquivo Comercial.pbip esta carregado")
        print("    3. Os dados foram atualizados (Pagina inicial > Atualizar)")
        sys.exit(1)
    print(f"  AS local na porta: {porta}")

    # 3. Executar queries
    print("\n[3/5] Executando consultas DAX...")
    try:
        raw = executar_query(porta, adomd)
    except RuntimeError as e:
        print(f"  [ERRO] {e}")
        print("")
        print("  Possiveis causas:")
        print("    - Power BI Desktop fechado ou com outro arquivo aberto")
        print("    - Dados ainda nao carregados (atualize o modelo primeiro)")
        print("    - Erro de permissao de execucao do PowerShell")
        sys.exit(1)

    # 4. Processar e salvar
    print("\n[4/5] Processando e salvando dims_ibratin.json...")
    dims = processar_dims(raw)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(dims, f, ensure_ascii=False, indent=2)

    print(f"  JSON salvo: {OUTPUT_JSON}")

    # 5. Patchear HTML diretamente
    print("\n[5/5] Atualizando gestor-campanhas.html...")
    html_ok = patch_html(dims)

    # Resumo
    print("\n" + "=" * 60)
    print("  CONCLUIDO")
    print("=" * 60)
    print(f"  Canais:    {len(dims['canal'])}")
    print(f"  Segmentos: {len(dims['segmento'])}")
    print(f"  Grupos:    {len(dims['grupo'])}")
    print(f"  Produtos:  {len(dims['produto'])}")
    print(f"  Empresas:  {len(dims.get('empresa', []))} {'(campo fFaturamento[EMPRESA] nao encontrado — preencha manualmente)' if not dims.get('empresa') else ''}")
    print(f"  Vendedores:{len(dims.get('vendedor', []))} {'(campo fFaturamento[VENDEDOR] nao encontrado — preencha manualmente)' if not dims.get('vendedor') else ''}")
    print("")
    if html_ok:
        print("  Proximo passo:")
        print("    Recarregue gestor-campanhas.html no navegador (F5).")
        print("    Os filtros ja estao com os dados reais do Power BI.")
    else:
        print("  Proximo passo:")
        print("    Abra gestor-campanhas.html, clique em 'Atualizar Dados'")
        print("    e selecione dims_ibratin.json.")


if __name__ == "__main__":
    main()
