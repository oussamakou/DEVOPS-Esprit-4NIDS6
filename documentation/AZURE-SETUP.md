# Azure setup: owner actions and reproducible deployment

There is no Azure subscription configured in this workspace. The local code cannot
create an account, accept Azure billing terms or choose a payment method for you.
Complete the account/billing steps yourself, then use these commands.

## 1. Check costs before creating anything

Create an Azure account/subscription and inspect its actual free credit terms.
Check your chosen region's prices and quota for Standard_B2s, a 32-GB managed disk,
a Standard static public IP, Basic ACR and outbound transfers. This combination is
not guaranteed free. Monitoring shares the VM, so do not choose a 1-GB VM for this lab.
Set a Cost Management budget/alert; a budget alerts you, it is not a hard spending cap.

Stopping an OS is different from deallocating its VM. Deallocation stops compute
billing but disks, public IP and registry can still cost money. Delete the lab with
Terraform when done, after saving any data you need.

Install Azure CLI from Microsoft's official instructions, and use PowerShell:

```powershell
az login
az account list --output table
az account set --subscription YOUR-SUBSCRIPTION-ID
```

Your identity needs permission to create the resources and assign Azure roles.
Creating the OIDC app also needs Entra application registration permission.
Do not grant subscription Owner to the GitHub identity.

## 2. Prepare Terraform and owner network access

```powershell
python scripts/install-tools.py terraform
ssh-keygen -t ed25519 -f "$env:USERPROFILE/.ssh/student-azure"
Copy-Item terraform/terraform.tfvars.example terraform/terraform.tfvars
```

Edit the ignored `terraform/terraform.tfvars` with your subscription ID, a globally
unique registry name, your public IPv4 followed by `/32` and the **contents of the
.pub public key file**. Do not paste a private key. Confirm your public IP using a
trusted source; a private Wi-Fi address such as 192.168.x.x will not work. If your ISP
changes your public IP, update `admin_cidr`, review the plan and apply again.

```powershell
.tools/terraform -chdir=terraform init
.tools/terraform -chdir=terraform fmt -check
.tools/terraform -chdir=terraform validate
python -m venv .tools/checkov-env
.tools/checkov-env/Scripts/python -m pip install checkov==3.3.29
.tools/checkov-env/Scripts/checkov --config-file .checkov.yml
.tools/terraform -chdir=terraform plan -out=lab.tfplan
# Read the complete plan. The next command creates billable resources.
.tools/terraform -chdir=terraform apply lab.tfplan
.tools/terraform -chdir=terraform output
```

Local state is acceptable for a solo first lab only. State and plan files can contain
sensitive data: keep them out of Git and keep a secure backup. Before adding automated
Terraform applies or another operator, migrate to an Azure Storage `azurerm` backend
with restricted access, encryption, versioning and state locking. The provided workflow
validates Terraform with `-backend=false`; it never applies infrastructure.

The VM's cloud-init installs a pinned k3s version, disables bundled ingress/load
balancer components and enables secret encryption. Its Pod/Service CIDRs differ from
the VNet CIDR. Check boot completion before your first application deployment:

```powershell
$ip = .tools/terraform -chdir=terraform output -raw public_ip
ssh -i "$env:USERPROFILE/.ssh/student-azure" "azureuser@$ip" 'sudo cloud-init status --wait; sudo k3s kubectl get nodes'
```

Network ports 22 and 30089 are allowed only from `admin_cidr`. Ports 6443, 3306,
9090 and 3000 stay closed to internet clients. Azure VM Run Command uses Azure's
control plane/VM agent and does not require opening SSH to GitHub runner IPs.

## 3. Set up GitHub and Azure OIDC

The existing repository is already on GitHub. Publish the reviewed project branch
and merge it through a PR when the non-deployment checks pass. Preserve the existing
Jenkinsfile as a historical alternative; disable its old automatic deployment trigger
if its Jenkins instance is still running to avoid two pipelines deploying independently.

After the Terraform apply, while logged in to Azure:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/configure-azure-oidc.ps1
```

This creates/reuses a user-assigned managed identity in the lab resource group, an
environment-specific federated credential, AcrPush and Reader scoped to the registry (the CLI must read registry
metadata), and a custom Run Command role assigned
only to this VM. Review the script before running it. It does not create a client
secret. If it reports existing objects, verify that their subject/permissions match
the repository you intend to deploy; the script rejects mismatched existing trust.
It does not need directory permissions to register an app. Azure permissions to
create managed identities and grant the scoped roles are still required. The
script registers `Microsoft.ManagedIdentity` if needed and leaves the identity and
federation inside the lab group, outside Terraform state.

In GitHub Settings -> Environments, create **azure-lab** and restrict deployment
branches to **master**. Add the printed identifiers as environment variables:

| Variable | Source |
| --- | --- |
| AZURE_CLIENT_ID | User-assigned managed identity clientId |
| AZURE_TENANT_ID | Azure account tenantId |
| AZURE_SUBSCRIPTION_ID | Azure subscription |
| AZURE_RESOURCE_GROUP | Terraform resource_group output |
| AZURE_VM_NAME | Terraform vm_name output |
| ACR_NAME | Terraform registry_name output |

At repository Settings -> Secrets and variables -> Actions -> Variables, add
**AZURE_DEPLOY_ENABLED=true**. This particular flag must be a repository variable
because the job's condition is evaluated before environment variables are loaded.
There is no DB_PASSWORD, registry admin password or Kubernetes admin kubeconfig in GitHub.

The Azure federated subject must be exactly:
`repo:oussamakou/DEVOPS-Esprit-4NIDS6:environment:azure-lab`, with issuer
`https://token.actions.githubusercontent.com` and audience `api://AzureADTokenExchange`.
If you fork/rename the repo, change the script argument and federated subject.

Protect master and require the five non-deploy checks. Avoid requiring a deployment
check that intentionally skips on pull requests. Some GitHub environment protection
features vary by plan and repository visibility.

## 4. Trigger and verify delivery

Push/merge to master or manually dispatch the workflow on master. Branch and PR runs
still test/scan, but never deploy. The first build can be slower due to downloads and
CVE database initialization. Azure role assignment propagation can also delay the
first registry authentication.

Open the Actions run: all gates must pass, then deployment must report
`DEPLOY_SUCCEEDED` for its image digest. Check the API from your allowed IP or use
an SSH tunnel (recommended even for the lab's synthetic data):

```powershell
$ip = .tools/terraform -chdir=terraform output -raw public_ip
ssh -i "$env:USERPROFILE/.ssh/student-azure" -N -L 8089:127.0.0.1:30089 "azureuser@$ip"
# In another terminal:
Invoke-RestMethod http://localhost:8089/student/students/getAllStudents
```

## 5. Clean up

First export any data/evidence you need and disable deployment by removing or setting
the repository variable AZURE_DEPLOY_ENABLED=false. Then:

```powershell
.tools/terraform -chdir=terraform plan -destroy -out=destroy.tfplan
# Confirm that only this lab is being removed, and that its data can be discarded.
.tools/terraform -chdir=terraform apply destroy.tfplan
```

Check the Azure portal for remaining billable resources and costs. Entra app
registrations, federated credentials and the custom role were created outside
Terraform and are **not** removed by terraform destroy. Remove only this project's
objects after verifying that nothing else uses them. Do not delete shared identities.

## Official references

- [Azure CLI installation](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows)
- [Azure pricing calculator](https://azure.microsoft.com/en-us/pricing/calculator/)
- [OIDC for GitHub Actions with Azure](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure)
- [Azure Linux VM Run Command](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/run-command)
- [ACR managed identity authentication](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-authentication-managed-identity)
- [Terraform Azure backend](https://developer.hashicorp.com/terraform/language/backend/azurerm)
