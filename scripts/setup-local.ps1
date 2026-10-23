$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$envPath = Join-Path $repoRoot '.env'
if (Test-Path -LiteralPath $envPath) {
    Write-Host '.env already exists; preserving your passwords.'
    exit 0
}
function New-LocalPassword {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes)
}
$content = "MYSQL_ROOT_PASSWORD=$(New-LocalPassword)`nDB_PASSWORD=$(New-LocalPassword)`n"
[IO.File]::WriteAllText($envPath, $content, [Text.UTF8Encoding]::new($false))
Write-Host 'Created ignored .env with separate random passwords. Keep it private.'
