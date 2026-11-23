terraform {
  required_version = "~> 1.13.0"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "= 5.14.0" }
  }
}

provider "azurerm" {
  features {}
  subscription_id                 = var.subscription_id
  storage_use_azuread             = true
  resource_provider_registrations = "none"
}

variable "subscription_id" {
  type    = string
  default = "910ebf13-1058-405d-b6cf-eda03e5288d1"
}

variable "deployment_principal_object_id" { type = string }

resource "azurerm_resource_group" "demo" {
  name     = "healthcare-data-ingestion-rg"
  location = "eastus"
  tags     = { project = "healthcare-data-ingestion", component = "terraform-state" }
  lifecycle { prevent_destroy = true }
}

resource "azurerm_storage_account" "state" {
  name                            = "hcingestiontfstate"
  resource_group_name             = azurerm_resource_group.demo.name
  location                        = azurerm_resource_group.demo.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false
  allow_nested_items_to_be_public = false
  blob_properties {
    versioning_enabled = true
    delete_retention_policy { days = 30 }
    container_delete_retention_policy { days = 30 }
  }
  lifecycle { prevent_destroy = true }
}

resource "azurerm_storage_container" "state" {
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"
  lifecycle { prevent_destroy = true }
  depends_on = [azurerm_role_assignment.state]
}

resource "azurerm_role_assignment" "state" {
  scope                = azurerm_storage_account.state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.deployment_principal_object_id
}

output "backend_configuration" {
  value = {
    resource_group_name  = azurerm_resource_group.demo.name
    storage_account_name = azurerm_storage_account.state.name
    container_name       = azurerm_storage_container.state.name
    key                  = "healthcare-bootstrap.tfstate"
    use_azuread_auth     = true
  }
}
