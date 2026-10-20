param(
    [string]$Repository = 'oussamakou/DEVOPS-Esprit-4NIDS6'
)
$ErrorActionPreference = 'Stop'
function Invoke-AzJson {
    param([string[]]$Arguments)
    $result = & az @Arguments --output json
    if ($LASTEXITCODE -ne 0) { throw 'Azure command failed; see output above.' }
    return ($result | ConvertFrom-Json)
}
if ($Repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') { throw 'Expected owner/repository.' }
$repoRoot = Split-Path $PSScriptRoot -Parent
$terraform = Join-Path $repoRoot '.tools\terraform.exe'
$rawOutputs = & $terraform "-chdir=$repoRoot\terraform" output -json
if ($LASTEXITCODE -ne 0) { throw 'Apply the Terraform configuration first.' }
$outputs = $rawOutputs | ConvertFrom-Json
$account = Invoke-AzJson -Arguments @('account', 'show')
$name = 'github-student-devsecops-' + ($Repository -replace '/', '-')
$apps = @(Invoke-AzJson -Arguments @('ad', 'app', 'list', '--display-name', $name))
if ($apps.Count -gt 1) { throw 'Multiple matching app registrations. Resolve them before continuing.' }
$app = if ($apps.Count -eq 1) { $apps[0] } else { Invoke-AzJson -Arguments @('ad', 'app', 'create', '--display-name', $name) }
$sp = & az ad sp show --id $app.appId --output json 2>$null
if ($LASTEXITCODE -ne 0) {
    $principal = Invoke-AzJson -Arguments @('ad', 'sp', 'create', '--id', $app.appId)
} else { $principal = $sp | ConvertFrom-Json }

$temporary = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString() + '.json')
try {
    $subject = "repo:${Repository}:environment:azure-lab"
    $credentials = @(Invoke-AzJson -Arguments @('ad', 'app', 'federated-credential', 'list', '--id', $app.id))
    if (-not ($credentials | Where-Object name -eq 'github-azure-lab')) {
        @{ name = 'github-azure-lab'; issuer = 'https://token.actions.githubusercontent.com'; subject = $subject; audiences = @('api://AzureADTokenExchange') } |
            ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding utf8
        $null = Invoke-AzJson -Arguments @('ad', 'app', 'federated-credential', 'create', '--id', $app.id, '--parameters', "@$temporary")
    }
    $roleName = 'Student Lab VM Deployment ' + $outputs.vm_name.value
    $existing = @(Invoke-AzJson -Arguments @('role', 'definition', 'list', '--name', $roleName))
    if ($existing.Count -eq 0) {
        @{ Name = $roleName; IsCustom = $true; Description = 'Run deployment scripts on the single lab VM. This is root-equivalent access to this VM.';
           Actions = @('Microsoft.Compute/virtualMachines/read', 'Microsoft.Compute/virtualMachines/runCommand/action');
           NotActions = @(); DataActions = @(); NotDataActions = @(); AssignableScopes = @("/subscriptions/$($account.id)") } |
            ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $temporary -Encoding utf8
        $null = Invoke-AzJson -Arguments @('role', 'definition', 'create', '--role-definition', "@$temporary")
    }
    foreach ($assignment in @(@{ Role = 'AcrPush'; Scope = $outputs.registry_id.value }, @{ Role = 'Reader'; Scope = $outputs.registry_id.value }, @{ Role = $roleName; Scope = $outputs.vm_id.value })) {
        $current = @(Invoke-AzJson -Arguments @('role', 'assignment', 'list', '--assignee', $principal.id, '--scope', $assignment.Scope, '--role', $assignment.Role))
        if ($current.Count -eq 0) {
            $null = Invoke-AzJson -Arguments @('role', 'assignment', 'create', '--assignee-object-id', $principal.id, '--assignee-principal-type', 'ServicePrincipal', '--role', $assignment.Role, '--scope', $assignment.Scope)
        }
    }
} finally { Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue }

Write-Host 'Create the GitHub environment azure-lab; restrict deployment branches to master.'
Write-Host 'Set these environment variables (identifiers, not passwords):'
@{
    AZURE_CLIENT_ID = $app.appId
    AZURE_TENANT_ID = $account.tenantId
    AZURE_SUBSCRIPTION_ID = $account.id
    AZURE_RESOURCE_GROUP = $outputs.resource_group.value
    AZURE_VM_NAME = $outputs.vm_name.value
    ACR_NAME = $outputs.registry_name.value
    AZURE_DEPLOY_ENABLED = 'true'
} | Format-Table -AutoSize
Write-Host 'AZURE_DEPLOY_ENABLED must be a repository variable because it controls job scheduling.'
