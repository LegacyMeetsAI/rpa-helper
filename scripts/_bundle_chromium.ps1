$src = "$env:LOCALAPPDATA\ms-playwright"
$dst = "e:\RPA_HELPER\dist\RPAHelper\_internal\playwright\driver\package\.local-browsers"

if (-not (Test-Path "$src\chromium-1223")) {
    Write-Error "Source chromium-1223 not found at $src"
    exit 1
}

New-Item -ItemType Directory -Force -Path $dst | Out-Null

Write-Host "Copying chromium-1223 ..."
Copy-Item -Recurse -Force "$src\chromium-1223" "$dst\chromium-1223"

Write-Host "Copying ffmpeg-1011 ..."
Copy-Item -Recurse -Force "$src\ffmpeg-1011" "$dst\ffmpeg-1011"

Write-Host "Copying chromium_headless_shell-1223 ..."
Copy-Item -Recurse -Force "$src\chromium_headless_shell-1223" "$dst\chromium_headless_shell-1223"

# Verify
$chromeExe = "$dst\chromium-1223\chrome-win64\chrome.exe"
if (Test-Path $chromeExe) {
    $size = (Get-Item $chromeExe).Length
    Write-Host ("OK chrome.exe: {0:N0} bytes" -f $size)
} else {
    Write-Error "chrome.exe missing after copy!"
    exit 1
}

# Show new total size
$total = (Get-ChildItem "e:\RPA_HELPER\dist\RPAHelper" -Recurse | Measure-Object -Property Length -Sum).Sum
Write-Host ("New total: {0} MB" -f [math]::Round($total/1MB, 1))
