# Prepara 7-Zip 25.01 (x64) en instalador\7zip (7z.exe, 7z.dll y License.txt) para abrir copias .rar.
# 7-Zip es de Igor Pavlov (GNU LGPL + restriccion unRAR); no forma parte de este repositorio.
#
# 0.0.5: puede construir SIN Internet. Por orden, usa la primera de estas fuentes que pase la comprobacion SHA-256:
#   1) la carpeta indicada en la variable CONTFACTU_7ZIP_DIR;
#   2) la copia ya comprobada que guarda este script en %LOCALAPPDATA%\ContFactu-build\7zip-25.01;
#   3) un 7-Zip 25.01 de 64 bits instalado en %ProgramFiles%\7-Zip;
#   4) la descarga de www.7-zip.org (y la guarda en 2 para la proxima vez).
# Nunca se usa un archivo cuyo SHA-256 no coincida con el de 7-Zip 25.01.
$ErrorActionPreference = "Stop"
$dest = Join-Path $PSScriptRoot "7zip"
$cache = Join-Path $env:LOCALAPPDATA "ContFactu-build\7zip-25.01"
$extraidos = @{   # SHA-256 de los archivos de 7-Zip 25.01 x64
  "7z.exe" = "4CD7D776C686427226A151789D2D61F0B2ED2C392148CC4E69C0238362FAFECF"
  "7z.dll" = "5BD20FB38499D95C39594F41D4781B6181B3304B7F1F4D06B0182F514E7EAA74"
}
$descargas = @{
  "7zr.exe"        = "256FECA8E274E5DA655E2A284FABAFD9F554365EB164862089DACD4E8276D282"
  "7z2501-x64.exe" = "78AFA2A1C773CAF3CF7EDF62F857D2A8A5DA55FB0FFF5DA416074C0D28B2B55F"
}
function Es-Valida($carpeta) {
  if (-not $carpeta -or -not (Test-Path (Join-Path $carpeta "License.txt"))) { return $false }
  foreach ($n in $extraidos.Keys) {
    $f = Join-Path $carpeta $n
    if (-not (Test-Path $f)) { return $false }
    if ((Get-FileHash $f -Algorithm SHA256).Hash -ne $extraidos[$n]) { return $false }
  }
  return $true
}
function Copiar($desde, $hacia) {
  New-Item -ItemType Directory -Force $hacia | Out-Null
  foreach ($n in @("7z.exe", "7z.dll", "License.txt")) { Copy-Item -Force (Join-Path $desde $n) (Join-Path $hacia $n) }
}
New-Item -ItemType Directory -Force $dest | Out-Null
foreach ($c in @($env:CONTFACTU_7ZIP_DIR, $cache, (Join-Path $env:ProgramFiles "7-Zip"))) {
  if (Es-Valida $c) {
    Copiar $c $dest
    Write-Host "7-Zip 25.01 comprobado (SHA-256) y copiado desde $c (sin descargar nada)"
    exit 0
  }
}
$tmp = Join-Path $env:TEMP ("contfactu-7zip-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force $tmp | Out-Null
try {
  foreach ($n in $descargas.Keys) {
    $f = Join-Path $tmp $n
    try { Invoke-WebRequest "https://www.7-zip.org/a/$n" -OutFile $f -UseBasicParsing }
    catch { throw "No se puede descargar 7-Zip de www.7-zip.org ($($_.Exception.Message)). Sin Internet: instale 7-Zip 25.01 de 64 bits o indique en CONTFACTU_7ZIP_DIR una carpeta con 7z.exe, 7z.dll y License.txt de esa version." }
    $h = (Get-FileHash $f -Algorithm SHA256).Hash
    if ($h -ne $descargas[$n]) { throw "SHA-256 incorrecto en $n ($h)" }
  }
  & (Join-Path $tmp "7zr.exe") x -y "-o$dest" (Join-Path $tmp "7z2501-x64.exe") 7z.exe 7z.dll License.txt | Out-Null
  if (-not (Es-Valida $dest)) { throw "Los archivos extraidos de 7-Zip no coinciden con los esperados" }
  try { Copiar $dest $cache } catch { Write-Host "Aviso: no se pudo guardar la copia local de 7-Zip ($($_.Exception.Message))" }
  Write-Host "7-Zip 25.01 descargado, comprobado y preparado en $dest"
} finally { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
