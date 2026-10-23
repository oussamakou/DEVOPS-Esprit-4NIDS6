# Offline integration checks: replace both native entry points; never contact Azure.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$target = Join-Path $PSScriptRoot 'configure-azure-oidc.ps1'
$toolName = if ([Environment]::OSVersion.Platform -eq 'Win32NT') { 'terraform.exe' } else { 'terraform' }
$mockTerraform = Join-Path (Join-Path $root '.tools') $toolName
$global:oidcTestgroupId = '/subscriptions/test-sub/resourceGroups/course-rg'
$global:oidcTestvmId = "$global:oidcTestgroupId/providers/Microsoft.Compute/virtualMachines/course-vm"
$global:oidcTestregistryId = "$global:oidcTestgroupId/providers/Microsoft.ContainerRegistry/registries/courseregistry"
$global:oidcTestidentity = @{ name = 'github-student-devsecops-oussamakou-DEVOPS-Esprit-4NIDS6'; clientId = 'test-client'; principalId = 'test-principal'; tenantId = 'test-tenant' }

function Assert-True($Condition, $Message) {
    if (-not $Condition) { throw $Message }
}
function Get-Flag($Values, $Name) {
    $index = [Array]::IndexOf($Values, $Name)
    if ($index -lt 0) { throw "Missing argument: $Name" }
    $Values[$index + 1]
}
function Reset-Scenario {
    $global:oidcTeststate = @{
        Commands = [Collections.Generic.List[object]]::new()
        Assignments = [Collections.Generic.List[object]]::new()
        Registered = $true; IdentityExists = $false; CredentialExists = $false; RoleExists = $false
        WrongTrust = $false; WrongSubscription = $false; DenyIdentity = $false; WrongTenant = $false
    }
}
function global:az {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$CommandArguments)
    $global:LASTEXITCODE = 0
    $global:oidcTeststate.Commands.Add($CommandArguments)
    $command = $CommandArguments[0..([Math]::Min(2, $CommandArguments.Count - 1))] -join ' '
    $result = switch -Wildcard ($command) {
        'account show *' { @{ id = $(if ($global:oidcTeststate.WrongSubscription) { 'another-sub' } else { 'test-sub' }); tenantId = 'test-tenant' }; break }
        'group show *' { @{ id = $global:oidcTestgroupId; location = 'spaincentral' }; break }
        'provider show *' { @{ registrationState = $(if ($global:oidcTeststate.Registered) { 'Registered' } else { 'NotRegistered' }) }; break }
        'provider register *' { $global:oidcTeststate.Registered = $true; @{}; break }
        'identity list *' { if ($global:oidcTeststate.IdentityExists) { $global:oidcTestidentity } else { @() }; break }
        'identity create *' {
            if ($global:oidcTeststate.DenyIdentity) { $global:LASTEXITCODE = 1; return }
            $global:oidcTeststate.IdentityExists = $true
            $created = $global:oidcTestidentity.Clone()
            if ($global:oidcTeststate.WrongTenant) { $created.tenantId = 'another-tenant' }
            $created; break
        }
        'identity federated-credential list' {
            if ($global:oidcTeststate.CredentialExists) {
                @{ name = 'github-azure-lab'; issuer = 'https://token.actions.githubusercontent.com';
                   subject = $(if ($global:oidcTeststate.WrongTrust) { 'repo:another/repo:environment:azure-lab' } else { 'repo:oussamakou/DEVOPS-Esprit-4NIDS6:environment:azure-lab' });
                   audiences = @('api://AzureADTokenExchange') }
            } else { @() }
            break
        }
        'identity federated-credential create' { $global:oidcTeststate.CredentialExists = $true; @{}; break }
        'role definition list' { if ($global:oidcTeststate.RoleExists) { @{ name = 'existing-role' } } else { @() }; break }
        'role definition create' {
            $file = (Get-Flag $CommandArguments '--role-definition').Substring(1)
            $global:oidcTestroleDefinition = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
            $global:oidcTeststate.RoleExists = $true; @{}; break
        }
        'role assignment list' {
            $scope = Get-Flag $CommandArguments '--scope'
            $role = Get-Flag $CommandArguments '--role'
            @($global:oidcTeststate.Assignments | Where-Object { $_.scope -eq $scope -and $_.role -eq $role }); break
        }
        'role assignment create' {
            $global:oidcTeststate.Assignments.Add(@{ principalId = (Get-Flag $CommandArguments '--assignee-object-id');
                scope = (Get-Flag $CommandArguments '--scope'); role = (Get-Flag $CommandArguments '--role') })
            @{}; break
        }
        default { throw "Unexpected Azure command (no network calls allowed): $command" }
    }
    if ($null -eq $result) { '[]' } else { ConvertTo-Json -InputObject $result -Depth 10 -Compress }
}
Set-Item -LiteralPath "Function:global:$mockTerraform" -Value {
    $global:LASTEXITCODE = 0
    @{
        vm_id = @{ value = $global:oidcTestvmId }; vm_name = @{ value = 'course-vm' }
        resource_group = @{ value = 'course-rg' }; registry_id = @{ value = $global:oidcTestregistryId }
        registry_name = @{ value = 'courseregistry' }; runtime = @{ value = 'compose' }
    } | ConvertTo-Json -Depth 5
}
function Invoke-Setup { & $target *> $null }
function Assert-SetupFails($Pattern) {
    $caught = $null
    try { Invoke-Setup } catch { $caught = $_ }
    Assert-True ($null -ne $caught -and $caught.ToString() -match $Pattern) "Expected setup to reject: $Pattern"
}
try {
    Reset-Scenario
    Invoke-Setup
    Assert-True ($global:oidcTeststate.Assignments.Count -eq 3) 'Expected registry push/read and VM deployment assignments'
    Assert-True ($global:oidcTeststate.Assignments[0].scope -eq $global:oidcTestregistryId) 'AcrPush must be registry-scoped'
    Assert-True ($global:oidcTeststate.Assignments[1].scope -eq $global:oidcTestregistryId) 'Reader must be registry-scoped'
    Assert-True ($global:oidcTeststate.Assignments[2].scope -eq $global:oidcTestvmId) 'Run Command must be single-VM scoped'
    Assert-True ($global:oidcTestroleDefinition.AssignableScopes[0] -eq $global:oidcTestgroupId) 'Custom role must be assignable only in the lab group'
    Assert-True (@($global:oidcTestroleDefinition.Actions).Count -eq 2) 'Custom role must not gain extra actions'
    Assert-True ($global:oidcTestroleDefinition.Actions -contains 'Microsoft.Compute/virtualMachines/read') 'Missing VM read permission'
    Assert-True ($global:oidcTestroleDefinition.Actions -contains 'Microsoft.Compute/virtualMachines/runCommand/action') 'Missing Run Command permission'
    $fic = @($global:oidcTeststate.Commands | Where-Object { $_[0] -eq 'identity' -and $_[1] -eq 'federated-credential' -and $_[2] -eq 'create' })
    Assert-True ($fic.Count -eq 1) 'Expected one federated credential'
    Assert-True ((Get-Flag $fic[0] '--subject') -ceq 'repo:oussamakou/DEVOPS-Esprit-4NIDS6:environment:azure-lab') 'Unexpected GitHub trust subject'
    Assert-True ((Get-Flag $fic[0] '--audiences') -ceq 'api://AzureADTokenExchange') 'Unexpected trust audience'
    Assert-True (@($global:oidcTeststate.Commands | Where-Object { $_[0] -eq 'ad' -or $_ -contains '--assignee' }).Count -eq 0) 'Setup must not require Graph resolution'
    foreach ($lookup in @($global:oidcTeststate.Commands | Where-Object { $_[0] -eq 'role' -and $_[1] -eq 'assignment' -and $_[2] -eq 'list' })) {
        Assert-True ((Get-Flag $lookup '--fill-principal-name') -eq 'false') 'Role lookups must not query Graph for principal names'
    }
    Write-Output 'PASS: new identity, exact trust and narrowly scoped roles without Graph'

    $firstCount = $global:oidcTeststate.Commands.Count
    Invoke-Setup
    $secondCommands = @($global:oidcTeststate.Commands | Select-Object -Skip $firstCount)
    Assert-True (@($secondCommands | Where-Object { $_ -contains 'create' }).Count -eq 0) 'Rerun must reuse existing objects'
    Write-Output 'PASS: rerun is idempotent'

    Reset-Scenario
    $global:oidcTeststate.IdentityExists = $true; $global:oidcTeststate.CredentialExists = $true; $global:oidcTeststate.WrongTrust = $true
    Assert-SetupFails 'trust does not match'
    Assert-True ($global:oidcTeststate.Assignments.Count -eq 0) 'Mismatched trust must stop before granting roles'
    Write-Output 'PASS: mismatched trust blocks role assignment'

    Reset-Scenario
    $global:oidcTeststate.WrongSubscription = $true
    Assert-SetupFails 'subscription differs'
    Assert-True ($global:oidcTeststate.Commands.Count -eq 1) 'Wrong subscription must stop before any resource operations'
    Write-Output 'PASS: wrong subscription stops before mutations'

    Reset-Scenario
    $global:oidcTeststate.DenyIdentity = $true
    Assert-SetupFails 'Azure command failed'
    Assert-True (-not $global:oidcTeststate.CredentialExists -and $global:oidcTeststate.Assignments.Count -eq 0) 'Denied identity creation must stop setup'
    Write-Output 'PASS: Azure failure cannot produce successful federation or roles'

    Reset-Scenario
    $global:oidcTeststate.WrongTenant = $true
    Assert-SetupFails 'tenant differs'
    Assert-True ($global:oidcTeststate.Assignments.Count -eq 0) 'Wrong tenant must stop before granting roles'
    Write-Output 'PASS: wrong identity tenant blocks setup'

    Reset-Scenario
    $global:oidcTeststate.Registered = $false
    Invoke-Setup
    Assert-True (@($global:oidcTeststate.Commands | Where-Object { $_[0] -eq 'provider' -and $_[1] -eq 'register' -and $_ -contains '--wait' }).Count -eq 1) 'Unregistered provider must be registered with wait'
    Write-Output 'PASS: missing Managed Identity provider is registered'
} finally {
    Remove-Item -LiteralPath "Function:global:$mockTerraform"
    Remove-Item -LiteralPath 'Function:global:az'
}
