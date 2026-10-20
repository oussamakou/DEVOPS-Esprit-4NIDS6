terraform {
  required_version = ">= 1.9, < 2.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
  # Local state for the first solo lab. See documentation/AZURE-SETUP.md before CI apply.
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}
