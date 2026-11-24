# Troca o Node.js 26 pelo Node.js 24 (o n8n precisa de pacotes nativos que só existem prontos para o 24).
# O Windows vai pedir permissão de administrador: clique em "Sim" em cada janela.
$ErrorActionPreference = "Continue"

$produto26 = "{7989E57E-52F7-45BE-9D87-E0C4C372752D}"  # Node.js 26.13.1 (do registro do Windows)
Write-Host "1/2  Removendo o Node.js 26... (aprove a janela do Windows)"
$remocao = Start-Process msiexec.exe -ArgumentList "/x $produto26 /passive /norestart" -Verb RunAs -Wait -PassThru
Write-Host "     código de saída: $($remocao.ExitCode)"
if ($remocao.ExitCode -notin 0, 1605, 3010) {   # 1605 = já não estava instalado; 3010 = pede reinício
    Write-Host "A remoção falhou. Nada mais foi alterado." -ForegroundColor Red
    exit $remocao.ExitCode
}

Write-Host "2/2  Instalando o Node.js 24... (aprove a janela do Windows, se aparecer)"
winget install --id OpenJS.NodeJS.24 -e --accept-source-agreements --accept-package-agreements
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
Write-Host "Node instalado: $(node --version)" -ForegroundColor Green
