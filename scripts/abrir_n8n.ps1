# Abre o n8n local em http://localhost:5678.
# Uso, na raiz do projeto:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\abrir_n8n.ps1 -Tunel https://xxxx.trycloudflare.com
# -Tunel: endereço do cloudflared apontado para a porta 5678. É por ele que a Meta entrega as
# mensagens; o n8n usa esse endereço para montar a "Production URL" dos webhooks.
# Sem -Tunel, o n8n abre só para uso local (a Meta não alcança).
param([string]$Tunel = "")
$ErrorActionPreference = "Stop"

# Recarrega o PATH do sistema: terminais abertos antes de instalar o Node não o enxergam.
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
if (-not (Get-Command n8n -ErrorAction SilentlyContinue)) {
    Write-Host "n8n não encontrado. Rode antes: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\instalar_n8n.ps1" -ForegroundColor Red
    exit 1
}

$env:GENERIC_TIMEZONE = "America/Sao_Paulo"
$env:TZ = "America/Sao_Paulo"
$env:N8N_DIAGNOSTICS_ENABLED = "false"        # não envia estatísticas de uso para a n8n
$env:N8N_PERSONALIZATION_ENABLED = "false"
# Só este computador abre o n8n: o túnel conecta por localhost, e ninguém da rede Wi-Fi acessa a porta 5678.
$env:N8N_LISTEN_ADDRESS = "127.0.0.1"
if ($Tunel) {
    if ($Tunel -notmatch '^https://') { Write-Host "-Tunel precisa começar com https://" -ForegroundColor Red; exit 1 }
    $env:N8N_WEBHOOK_URL = $Tunel.TrimEnd("/") + "/"
    $env:WEBHOOK_URL = $env:N8N_WEBHOOK_URL  # nome antigo, para versões anteriores do n8n
    Write-Host "Webhooks públicos em: $($env:N8N_WEBHOOK_URL)webhook/..."
} else {
    Write-Host "Sem -Tunel: a Meta não vai conseguir chamar este n8n." -ForegroundColor Yellow
}
Write-Host "Abrindo o n8n em http://localhost:5678 (Ctrl+C para parar)"
n8n start
