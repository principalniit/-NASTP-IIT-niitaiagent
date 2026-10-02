# One-command installer and upgrader for Windows (Docker Desktop). Linux and macOS:
# install.sh. Run from PowerShell in the repository folder:
#
#   powershell -ExecutionPolicy Bypass -File deploy\install.ps1
#   powershell -ExecutionPolicy Bypass -File deploy\install.ps1 -Yes -AdminEmail you@example.org -ProductName "Acme SEO"
#
# Running it again upgrades: secrets in deploy\.env are kept, images are rebuilt and the
# database schema is upgraded when the API starts. See deploy\README.md.
[CmdletBinding()]
param(
    [string]$ProductName = "",
    [string]$AdminEmail = "",
    [string]$AdminName = "Administrator",
    [string]$Url = "",
    [ValidateSet("", "yes", "no")][string]$AI = "",
    [string]$Model = "",
    [ValidateSet("", "yes", "no")][string]$Gpu = "",
    [string]$CaCert = "",
    [switch]$NoChromium,
    [switch]$Yes
)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Say($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "Error: $text" -ForegroundColor Red; exit 1 }
function Ask($question, $default) {
    if ($Yes) { return $default }
    $reply = Read-Host "$question [$default]"
    if ([string]::IsNullOrWhiteSpace($reply)) { return $default }
    return $reply.Trim()
}
function RandomText($length) {
    $chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789".ToCharArray()
    $bytes = New-Object byte[] $length
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}
function FernetKey {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_")
}
function EnvGet($name) {
    if (-not (Test-Path .env)) { return "" }
    $line = Get-Content .env | Where-Object { $_ -match "^$name=" } | Select-Object -Last 1
    if (-not $line) { return "" }
    return ($line -replace "^$name=", "").Trim('"')
}
function Run($exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { Fail "$exe $($arguments -join ' ') failed (exit $LASTEXITCODE)" }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail "Docker Desktop is not installed. Install it from docker.com first." }
docker compose version *> $null; if ($LASTEXITCODE -ne 0) { Fail "Docker Compose v2 is missing ('docker compose')." }
docker info *> $null; if ($LASTEXITCODE -ne 0) { Fail "Docker is not running. Start Docker Desktop, wait until it says 'Engine running', then run this again." }

$firstInstall = -not (Test-Path .env)
if (-not $firstInstall) {
    Say "Existing installation found: upgrading it (secrets in deploy\.env are kept)"
    if (-not $ProductName) { $ProductName = EnvGet "PRODUCT_NAME" }
    if (-not $Url) { $Url = EnvGet "PUBLIC_BASE_URL" }
    if (-not $AI) { $AI = if ((EnvGet "AI_PROVIDER") -eq "ollama") { "yes" } else { "no" } }
    if (-not $Model) { $Model = EnvGet "OLLAMA_DEFAULT_MODEL" }
    if (-not $Gpu) { $Gpu = if ((EnvGet "COMPOSE_FILE") -match "gpu") { "yes" } else { "no" } }
    if (-not $CaCert) { $CaCert = EnvGet "CA_CERT_FILE" }
    $jwt = EnvGet "JWT_SECRET"; $encKeys = EnvGet "INTEGRATIONS_ENCRYPTION_KEYS"; $dbPassword = EnvGet "DB_PASSWORD"
} else {
    if (-not $ProductName) { $ProductName = Ask "Product name shown on every screen" "AI SEO Agent" }
    if (-not $Url) { $Url = Ask "Address people will open" "http://localhost:3000" }
    if (-not $AI) { $AI = Ask "Include the local AI assistant (needs about 5 GB of disk)? yes/no" "yes" }
    $jwt = RandomText 64; $encKeys = FernetKey; $dbPassword = RandomText 32
}
if (-not $ProductName) { $ProductName = "AI SEO Agent" }
if (-not $Url) { $Url = "http://localhost:3000" }
$Url = $Url.TrimEnd("/")
if (-not $Model) { $Model = "qwen2.5:7b" }
$AI = if ($AI -match "^(y|yes)$") { "yes" } else { "no" }
if (-not $Gpu) {
    $Gpu = "no"
    if ($AI -eq "yes" -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
        nvidia-smi *> $null; if ($LASTEXITCODE -eq 0) { $Gpu = "yes" }
    }
}
if ($Url -notmatch "^https?://") { Fail "-Url must start with http:// or https://" }
if ($ProductName -match '["$`]') { Fail 'The product name cannot contain " $ or `' }

$uri = [Uri]$Url
$webPort = 3000; $webBind = "0.0.0.0"
if ($uri.Host -in @("localhost", "127.0.0.1")) {
    $webBind = "127.0.0.1"
    if (-not $uri.IsDefaultPort) { $webPort = $uri.Port }
}
if ($uri.Scheme -eq "https") {
    # A public name: the front proxy listens on 80 and 443 and gets a free certificate.
    if (-not $uri.IsDefaultPort) { Fail "Use an https:// address without a port, for example https://seo.example.org" }
    if ($uri.Host -match "^(localhost|127\.)" -or $uri.Host -notmatch "^[a-zA-Z0-9.-]+$") { Fail "HTTPS needs a public domain name that points at this server" }
    $environment = "production"; $cookieSecure = "true"
    $siteAddress = $uri.Host; $portsFile = "compose.https.yaml"
} else {
    $environment = "development"; $cookieSecure = "false"  # see install.sh
    $siteAddress = "http://:$webPort"; $portsFile = "compose.http.yaml"
}

$composeFile = "compose.yaml;$portsFile"
if ($Gpu -eq "yes") { $composeFile = "$composeFile;compose.gpu.yaml" }
$profiles = if ($AI -eq "yes") { "ai" } else { "" }
$aiProvider = if ($AI -eq "yes") { "ollama" } else { "none" }
$aiModel = if ($AI -eq "yes") { $Model } else { "" }
if ($CaCert -and $CaCert -ne "./no-extra-ca.crt") {
    if (-not (Test-Path $CaCert)) { Fail "CA certificate not found: $CaCert" }
    $CaCert = (Resolve-Path $CaCert).Path
} else { $CaCert = "./no-extra-ca.crt" }
$withChromium = if ($NoChromium) { "0" } else { "1" }

Say "Writing deploy\.env"
$content = @"
# Written by install.ps1. Keep this file private and back it up with the database:
# without INTEGRATIONS_ENCRYPTION_KEYS, stored credentials cannot be read.
COMPOSE_FILE=$composeFile
COMPOSE_PATH_SEPARATOR=;
COMPOSE_PROFILES=$profiles
PRODUCT_NAME="$ProductName"
PUBLIC_BASE_URL=$Url
CORS_ORIGINS=$Url
WEB_PORT=$webPort
WEB_BIND=$webBind
SITE_ADDRESS=$siteAddress
ENVIRONMENT=$environment
COOKIE_SECURE=$cookieSecure
JWT_SECRET=$jwt
INTEGRATIONS_ENCRYPTION_KEYS=$encKeys
DB_PASSWORD=$dbPassword
AI_PROVIDER=$aiProvider
OLLAMA_DEFAULT_MODEL=$aiModel
WITH_CHROMIUM=$withChromium
CA_CERT_FILE=$CaCert
"@
# UTF-8 without a byte-order mark: Docker Compose reads a BOM as part of the first name.
[IO.File]::WriteAllText((Join-Path $PSScriptRoot ".env"), $content.Replace("`r`n", "`n") + "`n", (New-Object Text.UTF8Encoding $false))

Say "Building and starting the containers (the first build takes several minutes)"
Run docker @("compose", "build")
Run docker @("compose", "up", "-d", "--wait", "--wait-timeout", "600")

if ($AI -eq "yes") {
    Say "Downloading the AI model $Model (several GB; skipped when already present)"
    Run docker @("compose", "exec", "-T", "ollama", "ollama", "pull", $Model)
}

if ($firstInstall) {
    if (-not $AdminEmail) { $AdminEmail = Ask "Administrator email" "" }
    if (-not $AdminEmail) { Fail "An administrator email is needed (-AdminEmail)." }
    Say "Creating the platform administrator $AdminEmail"
    if ($env:ADMIN_PASSWORD) {
        Run docker @("compose", "exec", "-T", "-e", "ADMIN_PASSWORD", "api", "python", "-m", "app.cli", "create-admin", "--email", $AdminEmail, "--name", $AdminName)
    } else {
        Run docker @("compose", "exec", "api", "python", "-m", "app.cli", "create-admin", "--email", $AdminEmail, "--name", $AdminName)
    }
}

Say "Done. Open $Url and sign in."
Write-Host "  Status:   cd deploy; docker compose ps"
Write-Host "  Logs:     cd deploy; docker compose logs -f api worker"
Write-Host "  Upgrade:  git pull; powershell -ExecutionPolicy Bypass -File deploy\install.ps1"
Write-Host "  Stop:     cd deploy; docker compose stop"
