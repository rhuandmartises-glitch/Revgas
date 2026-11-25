# Manda uma mensagem de texto pelo número de teste (ou pelo seu número) da WhatsApp Cloud API.
# Uso, na raiz do projeto:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\enviar_mensagem.ps1
#
# Regras da Meta:
# - O destinatário precisa estar na lista "Para" do número de teste (até 5 números verificados).
# - Texto livre só funciona até 24 h depois da última mensagem que ESSE número mandou para você.
#   Fora dessa janela, a Meta recusa (erro 131047) e só aceita modelo aprovado (ex.: hello_world).
# O token é digitado oculto e não fica salvo.
$ErrorActionPreference = "Stop"
$versao = "v26.0"

# Phone Number ID do .env (o número que envia). Pode digitar outro, se quiser.
$padrao = ""
if (Test-Path .env) {
    $linha = Select-String -Path .env -Pattern '^\s*WA_PHONE_NUMBER_ID=(\d+)' | Select-Object -First 1
    if ($linha) { $padrao = $linha.Matches[0].Groups[1].Value }
}
$idNumero = (Read-Host "Phone Number ID de quem envia [Enter = o do .env]").Trim()
if (-not $idNumero) { $idNumero = $padrao }
if ($idNumero -notmatch '^\d{6,25}$') { Write-Host "Phone Number ID inválido." -ForegroundColor Red; exit 1 }

$para = ((Read-Host "Para qual número (com DDI e DDD, ex.: 5586999999999)") -replace '\D', '')
if ($para.Length -lt 10) { Write-Host "Número inválido." -ForegroundColor Red; exit 1 }

$seguro = Read-Host "Token de acesso (não aparece na tela)" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro)
try { $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr).Trim() -replace '^Bearer\s+', '' }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }

$modo = (Read-Host "Tipo: [1] texto livre (dentro das 24 h)  [2] modelo hello_world (Enter = 1)").Trim()
if ($modo -eq "2") {
    $corpo = @{ messaging_product = "whatsapp"; to = $para; type = "template";
                template = @{ name = "hello_world"; language = @{ code = "en_US" } } }
} else {
    $texto = Read-Host "Mensagem"
    if (-not $texto) { Write-Host "Mensagem vazia." -ForegroundColor Red; exit 1 }
    $corpo = @{ messaging_product = "whatsapp"; to = $para; type = "text"; text = @{ body = $texto } }
}

try {
    $json = [Text.Encoding]::UTF8.GetBytes(($corpo | ConvertTo-Json -Depth 5 -Compress))
    $resposta = Invoke-RestMethod -Method Post -Uri "https://graph.facebook.com/$versao/$idNumero/messages" `
        -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json; charset=utf-8" -Body $json -TimeoutSec 30
    Write-Host "Enviada. Id: $($resposta.messages[0].id)" -ForegroundColor Green
} catch {
    $detalhe = $_.ErrorDetails.Message
    try { $erro = ($detalhe | ConvertFrom-Json).error; $detalhe = "($($erro.code)) $($erro.message)" } catch {}
    Write-Host "A Meta recusou: $detalhe" -ForegroundColor Red
    if ($detalhe -match '131047') { Write-Host "Passaram 24 h da última mensagem desse número: use a opção 2 (modelo)." }
    if ($detalhe -match '131030') { Write-Host "Esse número não está na lista 'Para'. Cadastre e verifique no painel da Meta." }
    if ($detalhe -match '\(190\)') { Write-Host "Token inválido ou expirado: gere outro no painel." }
    exit 1
} finally {
    $token = $null
}
