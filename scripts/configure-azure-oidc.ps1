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
$toolName = if ([Environment]::OSVersion.Platform -eq 'Win32NT') { 'terraform.exe' } else { 'terraform' }
$terraform = Join-Path (Join-Path $repoRoot '.tools') $toolName
$terraformDirectory = Join-Path $repoRoot 'terraform'
$rawOutputs = & $terraform "-chdir=$terraformDirectory" output -json
if ($LASTEXITCODE -ne 0) { throw 'Apply the Terraform configuration first.' }
$outputs = $rawOutputs | ConvertFrom-Json
$account = Invoke-AzJson -Arguments @('account', 'show')
if ($outputs.vm_id.value -notlike "/subscriptions/$($account.id)/*") {
    throw 'The signed-in subscription differs from the Terraform VM. Select the correct Azure subscription first.'
}
$resourceGroup = $outputs.resource_group.value
$group = Invoke-AzJson -Arguments @('group', 'show', '--name', $resourceGroup)
$name = 'github-student-devsecops-' + ($Repository -replace '/', '-')
# Managed identities are Azure resources; no Microsoft Graph app-registration rights are needed.
Write-Host '[1/4] Checking the Managed Identity resource provider...'
$provider = Invoke-AzJson -Arguments @('provider', 'show', '--namespace', 'Microsoft.ManagedIdentity')
if ($provider.registrationState -ne 'Registered') {
    Write-Host 'Registering Microsoft.ManagedIdentity; this can take a few minutes...'
    $null = Invoke-AzJson -Arguments @('provider', 'register', '--namespace', 'Microsoft.ManagedIdentity', '--wait')
}
Write-Host '[2/4] Creating or reusing the GitHub user-assigned managed identity...'
$identities = @(Invoke-AzJson -Arguments @('identity', 'list', '--resource-group', $resourceGroup))
$matching = @($identities | Where-Object name -eq $name)
if ($matching.Count -gt 1) { throw 'Multiple matching managed identities. Resolve them before continuing.' }
$identity = if ($matching.Count -eq 1) { $matching[0] } else {
    Invoke-AzJson -Arguments @('identity', 'create', '--name', $name, '--resource-group', $resourceGroup, '--location', $group.location)
}
if (-not $identity.clientId -or -not $identity.principalId -or $identity.tenantId -ne $account.tenantId) {
    throw 'Managed identity identifiers are missing or its tenant differs from the signed-in account.'
}

$temporary = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString() + '.json')
try {
    Write-Host '[3/4] Configuring trust for the azure-lab GitHub environment...'
    $subject = "repo:${Repository}:environment:azure-lab"
    $credentials = @(Invoke-AzJson -Arguments @('identity', 'federated-credential', 'list', '--identity-name', $name, '--resource-group', $resourceGroup))
    $credential = @($credentials | Where-Object name -eq 'github-azure-lab')
    if ($credential.Count -gt 1) { throw 'Multiple matching federated credentials. Resolve them before continuing.' }
    if ($credential.Count -eq 1) {
        if ($credential[0].issuer -cne 'https://token.actions.githubusercontent.com' -or
            $credential[0].subject -cne $subject -or
            @($credential[0].audiences).Count -ne 1 -or
            $credential[0].audiences[0] -cne 'api://AzureADTokenExchange') {
            throw 'Existing federated trust does not match this repository/environment. Review it before continuing.'
        }
    } else {
        $null = Invoke-AzJson -Arguments @('identity', 'federated-credential', 'create', '--name', 'github-azure-lab',
            '--identity-name', $name, '--resource-group', $resourceGroup,
            '--issuer', 'https://token.actions.githubusercontent.com', '--subject', $subject,
            '--audiences', 'api://AzureADTokenExchange')
    }
    Write-Host '[4/4] Assigning registry and single-VM deployment permissions...'
    $roleName = 'Student Lab VM Deployment ' + $outputs.vm_name.value
    $existing = @(Invoke-AzJson -Arguments @('role', 'definition', 'list', '--name', $roleName))
    if ($existing.Count -eq 0) {
        @{ Name = $roleName; IsCustom = $true; Description = 'Run deployment scripts on the single lab VM. This is root-equivalent access to this VM.';
           Actions = @('Microsoft.Compute/virtualMachines/read', 'Microsoft.Compute/virtualMachines/runCommand/action');
           NotActions = @(); DataActions = @(); NotDataActions = @(); AssignableScopes = @($group.id) } |
            ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $temporary -Encoding utf8
        $null = Invoke-AzJson -Arguments @('role', 'definition', 'create', '--role-definition', "@$temporary")
    }
    foreach ($assignment in @(@{ Role = 'AcrPush'; Scope = $outputs.registry_id.value }, @{ Role = 'Reader'; Scope = $outputs.registry_id.value }, @{ Role = $roleName; Scope = $outputs.vm_id.value })) {
        # Filter ARM results by principal ID instead of resolving an assignee through Microsoft Graph.
        $assigned = @(Invoke-AzJson -Arguments @('role', 'assignment', 'list', '--scope', $assignment.Scope, '--role', $assignment.Role, '--fill-principal-name', 'false'))
        $current = @($assigned | Where-Object principalId -eq $identity.principalId)
        if ($current.Count -eq 0) {
            $null = Invoke-AzJson -Arguments @('role', 'assignment', 'create', '--assignee-object-id', $identity.principalId, '--assignee-principal-type', 'ServicePrincipal', '--role', $assignment.Role, '--scope', $assignment.Scope)
        }
    }
} finally { Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue }

Write-Host 'Create the GitHub environment azure-lab; restrict deployment branches to master.'
Write-Host 'Set these environment variables (identifiers, not passwords):'
$settings = @{
    AZURE_CLIENT_ID = $identity.clientId
    AZURE_TENANT_ID = $account.tenantId
    AZURE_SUBSCRIPTION_ID = $account.id
    AZURE_RESOURCE_GROUP = $outputs.resource_group.value
    AZURE_VM_NAME = $outputs.vm_name.value
    ACR_NAME = $outputs.registry_name.value
    AZURE_DEPLOY_ENABLED = 'true'
}
if ($outputs.runtime.value -eq 'compose') {
    $settings['COMPOSE_VM_NAME'] = $outputs.vm_name.value
    $settings['AZURE_DEPLOY_ENABLED'] = 'false'
}
$settings | Format-Table -AutoSize
Write-Host 'AZURE_DEPLOY_ENABLED must be a repository variable because it controls job scheduling.'
