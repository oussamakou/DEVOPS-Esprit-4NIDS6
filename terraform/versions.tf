terraform {
  required_version = ">= 1.9, < 2.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.10"
    }
  }
  # Local state for the first solo lab. See documentation/AZURE-SETUP.md before CI apply.
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  # The Cloud Shell preparation step registers exactly the three services used
  # by the coursework path, rather than auto-registering unrelated providers.
  resource_provider_registrations = var.runtime == "compose" ? "none" : "legacy"
}
