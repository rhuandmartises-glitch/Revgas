# Instala o n8n localmente, do zero (precisa do Node.js 24; o 26 ainda não tem os módulos nativos prontos).
# Uso, na raiz do projeto:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\instalar_n8n.ps1
$ErrorActionPreference = "Stop"
$VERSAO_N8N = "2.49.5"

# Recarrega o PATH do sistema: terminais abertos antes de instalar o Node não o enxergam.
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js não encontrado. Instale com:  winget install OpenJS.NodeJS.24" -ForegroundColor Red
    exit 1
}
$maior = [int]((node --version).TrimStart("v").Split(".")[0])
if ($maior -ne 24) {
    Write-Host "Use o Node.js 24 (encontrado: $(node --version)). Veja scripts\trocar_para_node24.ps1." -ForegroundColor Red
    exit 1
}

# Instalação limpa: uma instalação interrompida antes deixa arquivos cortados pela metade.
$prefixo = (npm prefix -g).Trim()
$pasta = Join-Path $prefixo "node_modules\n8n"
if (Test-Path -LiteralPath $pasta) {
    Write-Host "Removendo instalação anterior do n8n..."
    Remove-Item -Recurse -Force -LiteralPath $pasta -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $pasta) { cmd /c "rmdir /s /q `"$pasta`"" }
    if (Test-Path -LiteralPath $pasta) {
        Write-Host "Não consegui apagar $pasta (algum n8n aberto?). Feche o n8n e rode de novo." -ForegroundColor Red
        exit 1
    }
    Remove-Item -Force (Join-Path $prefixo "n8n"), (Join-Path $prefixo "n8n.cmd"), (Join-Path $prefixo "n8n.ps1") -ErrorAction SilentlyContinue
}
npm cache verify | Out-Null

# O npm 11 não roda scripts de instalação sem permissão. Liberamos só os módulos nativos que o n8n usa.
# Ficam de fora: @scarf/scarf (envia estatísticas de uso) e agent-browser (baixaria um navegador inteiro).
$permitidos = @(
    "sqlite3", "isolated-vm", "@parcel/watcher", "msgpackr-extract", "protobufjs", "ssh2",
    "@sentry/node-native-stacktrace", "@sentry/node-cpu-profiler", "@confluentinc/kafka-javascript", "vue-demi", "oracledb"
) -join ","

Write-Host "Node $(node --version) / npm $(npm --version)"
Write-Host "Instalando o n8n $VERSAO_N8N (pode levar alguns minutos)..."
npm install -g "n8n@$VERSAO_N8N" --no-fund --no-audit "--allow-scripts=$permitidos"
if ($LASTEXITCODE -ne 0) {
    Write-Host "A instalação do n8n falhou (código $LASTEXITCODE). Veja as mensagens acima." -ForegroundColor Red
    exit $LASTEXITCODE
}

# Confere se o n8n carrega de verdade (não só se o arquivo existe).
$versao = n8n --version
n8n list:workflow | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "O n8n foi instalado, mas não carregou. Veja as mensagens acima." -ForegroundColor Red
    exit 1
}
Write-Host "n8n $versao instalado e funcionando." -ForegroundColor Green
