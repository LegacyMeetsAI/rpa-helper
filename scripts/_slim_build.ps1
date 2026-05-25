$path = "e:\RPA_HELPER\dist\RPAHelper\_internal\playwright\driver\package\.local-browsers\chromium_headless_shell-1223"
Remove-Item -Recurse -Force $path
$total = (Get-ChildItem "e:\RPA_HELPER\dist\RPAHelper" -Recurse | Measure-Object -Property Length -Sum).Sum
Write-Host ("Removed. New total: {0} MB" -f [math]::Round($total/1MB, 1))
