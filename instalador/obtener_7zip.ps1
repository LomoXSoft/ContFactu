# Descarga 7-Zip 25.01 (x64) de www.7-zip.org, comprueba su SHA-256 y extrae 7z.exe, 7z.dll y License.txt
# en instalador\7zip. 7-Zip es de Igor Pavlov (GNU LGPL + restriccion unRAR); no forma parte de este repositorio.
$ErrorActionPreference = "Stop"
$dest = Join-Path $PSScriptRoot "7zip"
$tmp = Join-Path $env:TEMP ("contfactu-7zip-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force $dest, $tmp | Out-Null
$archivos = @{
  "7zr.exe"        = "256FECA8E274E5DA655E2A284FABAFD9F554365EB164862089DACD4E8276D282"
  "7z2501-x64.exe" = "78AFA2A1C773CAF3CF7EDF62F857D2A8A5DA55FB0FFF5DA416074C0D28B2B55F"
}
try {
  foreach ($n in $archivos.Keys) {
    $f = Join-Path $tmp $n
    Invoke-WebRequest "https://www.7-zip.org/a/$n" -OutFile $f -UseBasicParsing
    $h = (Get-FileHash $f -Algorithm SHA256).Hash
    if ($h -ne $archivos[$n]) { throw "SHA-256 incorrecto en $n ($h)" }
  }
  & (Join-Path $tmp "7zr.exe") x -y "-o$dest" (Join-Path $tmp "7z2501-x64.exe") 7z.exe 7z.dll License.txt | Out-Null
  if (-not (Test-Path (Join-Path $dest "7z.exe"))) { throw "No se pudo extraer 7z.exe" }
  Write-Host "7-Zip 25.01 preparado en $dest"
} finally { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
