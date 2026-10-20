$ErrorActionPreference = 'Stop'
$vendorFolder = Join-Path $PSScriptRoot 'vendor'
New-Item -ItemType Directory -Force -Path $vendorFolder | Out-Null
$vendorInstaller = Join-Path $vendorFolder 'MicrosoftEdgeWebview2Setup.exe'
Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $vendorInstaller
$signature = Get-AuthenticodeSignature -LiteralPath $vendorInstaller
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { throw 'Assinatura Microsoft inválida.' }
Write-Output 'Componente WebView2 oficial conferido.'
