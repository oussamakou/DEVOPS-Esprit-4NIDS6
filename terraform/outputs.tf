output "resource_group" { value = azurerm_resource_group.lab.name }
output "vm_name" { value = azurerm_linux_virtual_machine.lab.name }
output "vm_id" { value = azurerm_linux_virtual_machine.lab.id }
output "registry_id" { value = azurerm_container_registry.lab.id }
output "registry_name" { value = azurerm_container_registry.lab.name }
output "registry_server" { value = azurerm_container_registry.lab.login_server }
output "public_ip" { value = azurerm_public_ip.lab.ip_address }
output "api_url" { value = var.runtime == "compose" ? "Use SSH tunnel to 127.0.0.1:8089" : "http://${azurerm_public_ip.lab.ip_address}:30089/student/students/getAllStudents" }
output "tools_public_ip" { value = try(azurerm_public_ip.tools[0].ip_address, null) }
output "tools_fqdn" { value = try(azurerm_public_ip.tools[0].fqdn, null) }
output "runtime" { value = var.runtime }
