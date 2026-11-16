param([Parameter(Mandatory=$true)][string]$LanIP, [int]$HttpsPort=8443, [int]$MqttPort=8883)
$ErrorActionPreference = 'Stop'
$ip = $null
if (-not [Net.IPAddress]::TryParse($LanIP, [ref]$ip) -or $ip.AddressFamily -ne 'InterNetwork') { throw 'LanIP must be your computer IPv4 address on the ESP32 Wi-Fi network.' }
$projectRoot = Split-Path -Parent $PSScriptRoot
$target = Join-Path $projectRoot '.env'
if (Test-Path -LiteralPath $target) { throw '.env already exists; kept unchanged. Edit it manually if needed.' }
function New-RandomHex {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
}
$lines = @(
    "JWT_SECRET=$(New-RandomHex)",
    'MQTT_USERNAME=backend',
    "MQTT_PASSWORD=$(New-RandomHex)",
    'MQTT_ADMIN_USERNAME=wms-admin',
    "MQTT_ADMIN_PASSWORD=$(New-RandomHex)",
    "MYSQL_ROOT_PASSWORD=$(New-RandomHex)",
    "MYSQL_PASSWORD=$(New-RandomHex)",
    "HTTPS_PORT=$HttpsPort",
    "MQTT_TLS_PORT=$MqttPort",
    "WS_ALLOWED_ORIGINS=https://localhost:${HttpsPort},https://127.0.0.1:${HttpsPort},https://${LanIP}:${HttpsPort}"
)
$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv and install tools/requirements.txt first.' }
& $python (Join-Path $PSScriptRoot 'generate_certs.py') --host $LanIP
if ($LASTEXITCODE -ne 0) { throw 'Certificate generation failed; .env was not written.' }
[System.IO.File]::WriteAllLines($target, $lines, (New-Object System.Text.UTF8Encoding($false)))
Write-Output "Created .env and TLS certs. Next: docker compose up --build -d. UI: https://${LanIP}:${HttpsPort}"
