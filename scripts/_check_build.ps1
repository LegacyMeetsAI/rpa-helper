$root = "e:/RPA_HELPER/dist/RPAHelper"
$sum = (Get-ChildItem $root -Recurse | Measure-Object -Property Length -Sum).Sum
$mb = [math]::Round($sum/1MB, 1)
Write-Host ("Total size: {0} MB" -f $mb)
$exe = Get-Item "$root/RPAHelper.exe"
Write-Host ("exe: {0:N0} bytes  modified {1}" -f $exe.Length, $exe.LastWriteTime)
$pw = "$root/_internal/playwright"
Write-Host ("playwright bundled: " + (Test-Path $pw))
$node = "$root/_internal/playwright/driver/node.exe"
Write-Host ("node driver: " + (Test-Path $node))
$cfgs = Get-ChildItem "$root/config" -Filter *.yaml | Select-Object -ExpandProperty Name
Write-Host ("configs: " + ($cfgs -join ', '))
