param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$exampleFile = Join-Path $projectRoot ".env.example"
$projectEnvFile = Join-Path $projectRoot ".env"

if (Test-Path -LiteralPath $projectEnvFile) {
    throw "A .env file already exists. It was left untouched; keep its secrets private."
}

if (-not (Test-Path -LiteralPath $exampleFile)) {
    throw "Missing .env.example at the project root."
}

$secretGenerator = "import secrets; print(secrets.token_urlsafe(36))"
$generatedSecrets = @()
for ($index = 0; $index -lt 5; $index++) {
    $generatedSecret = & py -3.12 -c $secretGenerator
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($generatedSecret)) {
        throw "Could not generate a secret. Confirm Python 3.12 is installed."
    }
    $generatedSecrets += $generatedSecret.Trim()
}

$environmentText = [System.IO.File]::ReadAllText($exampleFile)
$environmentText = [regex]::Replace($environmentText, "(?m)^POSTGRES_PASSWORD=.*$", "POSTGRES_PASSWORD=$($generatedSecrets[0])")
$environmentText = [regex]::Replace($environmentText, "(?m)^DEMO_OPERATOR_TOKEN=.*$", "DEMO_OPERATOR_TOKEN=$($generatedSecrets[1])")
$environmentText = [regex]::Replace($environmentText, "(?m)^DEMO_VIEWER_TOKEN=.*$", "DEMO_VIEWER_TOKEN=$($generatedSecrets[2])")
$environmentText = [regex]::Replace($environmentText, "(?m)^AGENTARTS_MCP_API_KEY=.*$", "AGENTARTS_MCP_API_KEY=$($generatedSecrets[3])")
$environmentText = [regex]::Replace($environmentText, "(?m)^ICT_INTERNAL_API_KEY=.*$", "ICT_INTERNAL_API_KEY=$($generatedSecrets[4])")
[System.IO.File]::WriteAllText($projectEnvFile, $environmentText, [System.Text.UTF8Encoding]::new($false))

Write-Host "Created .env with five different random values. Do not upload or share this file."
