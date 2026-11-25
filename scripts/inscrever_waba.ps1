# Inscreve a conta do WhatsApp Business (WABA) no seu app da Meta, para as mensagens reais chegarem ao webhook.
# Sintoma que isto resolve: o botão "Testar" do webhook chega no n8n, mas as mensagens do celular não chegam.
#
# Uso, na raiz do projeto:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\inscrever_waba.ps1
# Pede o ID da conta do WhatsApp Business (WhatsApp -> Configuração da API, "ID da conta do WhatsApp Business")
# e o token de acesso. O token é digitado oculto e não fica salvo em lugar nenhum.
$ErrorActionPreference = "Stop"
$versao = "v26.0"

$waba = (Read-Host "ID da conta do WhatsApp Business (só números)").Trim()
if ($waba -notmatch '^\d{6,25}$') { Write-Host "Esse ID não parece certo: use só os números." -ForegroundColor Red; exit 1 }

$seguro = Read-Host "Token de acesso (cole e aperte Enter; não aparece na tela)" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro)
try { $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr).Trim() -replace '^Bearer\s+', '' }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
if (-not $token.StartsWith("EAA")) { Write-Host "O token deveria começar com EAA." -ForegroundColor Red; exit 1 }

$cabecalho = @{ Authorization = "Bearer $token" }
$url = "https://graph.facebook.com/$versao/$waba/subscribed_apps"
try {
    $inscricao = Invoke-RestMethod -Method Post -Uri $url -Headers $cabecalho -TimeoutSec 30
    Write-Host "Inscrição: $(if ($inscricao.success) { 'feita' } else { 'resposta inesperada' })" -ForegroundColor Green
    $lista = Invoke-RestMethod -Method Get -Uri $url -Headers $cabecalho -TimeoutSec 30
    $apps = @($lista.data | ForEach-Object { $_.whatsapp_business_api_data.name })
    Write-Host "Apps inscritos nesta conta: $(if ($apps) { $apps -join ', ' } else { 'nenhum' })"
} catch {
    $detalhe = $_.ErrorDetails.Message
    if ($detalhe) { try { $detalhe = ($detalhe | ConvertFrom-Json).error.message } catch {} }
    Write-Host "A Meta recusou: $detalhe" -ForegroundColor Red
    exit 1
} finally {
    $token = $null; $cabecalho = $null
}
