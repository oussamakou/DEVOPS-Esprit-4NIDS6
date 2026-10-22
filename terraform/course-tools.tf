# Optional dedicated host: SonarQube/Nexus must not compete with the 4 GB app VM.
resource "azurerm_subnet" "tools" {
  count                = var.enable_course_tools ? 1 : 0
  name                 = "course-tools"
  resource_group_name  = azurerm_resource_group.lab.name
  virtual_network_name = azurerm_virtual_network.lab.name
  address_prefixes     = ["10.42.2.0/24"]
}

resource "azurerm_network_security_group" "tools" {
  count               = var.enable_course_tools ? 1 : 0
  name                = "${var.prefix}-tools-nsg"
  resource_group_name = azurerm_resource_group.lab.name
  location            = var.location
  tags                = local.tags
}

resource "azurerm_network_security_rule" "tools_ssh" {
  count                       = var.enable_course_tools ? 1 : 0
  name                        = "SSH-from-owner-only"
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = var.admin_cidr
  destination_address_prefix  = "*"
  resource_group_name         = azurerm_resource_group.lab.name
  network_security_group_name = azurerm_network_security_group.tools[0].name
}

resource "azurerm_network_security_rule" "tools_https" {
  count                       = var.enable_course_tools ? 1 : 0
  name                        = "HTTPS-and-ACME-for-authenticated-tools"
  priority                    = 110
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_ranges     = ["80", "443", "8443"]
  source_address_prefix       = "Internet"
  destination_address_prefix  = "*"
  resource_group_name         = azurerm_resource_group.lab.name
  network_security_group_name = azurerm_network_security_group.tools[0].name
}

resource "azurerm_subnet_network_security_group_association" "tools" {
  count                     = var.enable_course_tools ? 1 : 0
  subnet_id                 = azurerm_subnet.tools[0].id
  network_security_group_id = azurerm_network_security_group.tools[0].id
}

resource "azurerm_public_ip" "tools" {
  count               = var.enable_course_tools ? 1 : 0
  name                = "${var.prefix}-tools-ip"
  resource_group_name = azurerm_resource_group.lab.name
  location            = var.location
  allocation_method   = "Static"
  sku                 = "Standard"
  domain_name_label   = "${var.prefix}-${substr(sha256(var.registry_name), 0, 8)}-tools"
  tags                = local.tags
}

resource "azurerm_network_interface" "tools" {
  count               = var.enable_course_tools ? 1 : 0
  name                = "${var.prefix}-tools-nic"
  resource_group_name = azurerm_resource_group.lab.name
  location            = var.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.tools[0].id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.tools[0].id
  }
  tags = local.tags
}

resource "azurerm_linux_virtual_machine" "tools" {
  count                           = var.enable_course_tools ? 1 : 0
  name                            = "${var.prefix}-tools-vm"
  resource_group_name             = azurerm_resource_group.lab.name
  location                        = var.location
  size                            = var.tools_vm_size
  admin_username                  = "azureuser"
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.tools[0].id]
  secure_boot_enabled             = true
  vtpm_enabled                    = true
  patch_mode                      = "AutomaticByPlatform"
  patch_assessment_mode           = "AutomaticByPlatform"
  provision_vm_agent              = true
  custom_data                     = base64encode(file("${path.module}/../cloud/docker-cloud-init.yaml"))
  admin_ssh_key {
    username   = "azureuser"
    public_key = var.ssh_public_key
  }
  identity { type = "SystemAssigned" }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 128
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
  boot_diagnostics {}
  tags       = local.tags
  depends_on = [azurerm_subnet_network_security_group_association.tools]
}
