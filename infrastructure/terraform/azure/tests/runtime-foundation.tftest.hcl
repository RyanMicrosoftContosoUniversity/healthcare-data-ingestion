mock_provider "azurerm" {
  mock_data "azurerm_resource_group" {
    defaults = {
      id       = "/subscriptions/910ebf13-1058-405d-b6cf-eda03e5288d1/resourceGroups/healthcare-data-ingestion-rg"
      name     = "healthcare-data-ingestion-rg"
      location = "eastus"
    }
  }
}
mock_provider "azapi" {}
mock_provider "azuread" {}

variables {
  alert_email                  = "notifications@example.test"
  budget_start_date            = "2026-11-01T00:00:00Z"
  provision_runtime_principals = true
}

run "managed_runtime_foundation" {
  command = plan

  assert {
    condition     = length(azuread_application.runtime) == 4 && length(azuread_service_principal.runtime) == 4
    error_message = "Create exactly the four approved runtime applications and service principals."
  }
  assert {
    condition     = length(azurerm_key_vault_certificate.runtime) == 4 && length(azuread_application_certificate.runtime) == 4
    error_message = "Every new principal requires its own vault-generated public certificate registration."
  }
  assert {
    condition = alltrue([
      for certificate in values(azurerm_key_vault_certificate.runtime) :
      length(certificate.certificate) == 0
    ])
    error_message = "Vault generation must not import private certificate contents through Terraform."
  }
  assert {
    condition     = azurerm_key_vault.runtime.purge_protection_enabled && azurerm_key_vault.runtime.rbac_authorization_enabled
    error_message = "The runtime vault must retain purge protection and Azure RBAC."
  }
  assert {
    condition     = length(azurerm_mssql_firewall_rule.administrator) == 0
    error_message = "No personal SQL firewall access is permitted without an explicit public IPv4."
  }
  assert {
    condition = alltrue([
      for application in values(azuread_application.runtime) :
      application.owners == toset([var.deployment_principal_object_id])
    ])
    error_message = "The deployment principal must own every runtime application."
  }
}

run "external_runtime_principals" {
  command = plan
  variables {
    provision_runtime_principals = false
    runtime_principal_object_ids = {
      control       = "11111111-1111-4111-8111-111111111111"
      source-reader = "22222222-2222-4222-8222-222222222222"
      diagnostics   = "33333333-3333-4333-8333-333333333333"
      orchestrator  = "44444444-4444-4444-8444-444444444444"
    }
    admin_ipv4 = "203.0.113.10"
  }
  assert {
    condition     = length(azuread_service_principal.runtime) == 0 && length(azurerm_key_vault_certificate.runtime) == 0
    error_message = "External-principal deployments must not silently create replacement identities."
  }
  assert {
    condition     = azurerm_role_assignment.runtime_log_publisher.principal_id == var.runtime_principal_object_ids["diagnostics"]
    error_message = "Existing runtime grants must retain their supplied principal."
  }
  assert {
    condition     = length(azurerm_mssql_firewall_rule.administrator) == 2 && azurerm_mssql_firewall_rule.administrator["clarity"].start_ip_address == var.admin_ipv4
    error_message = "An explicit approved IPv4 should allow administration on both source servers."
  }
}

run "reject_invalid_administrator_address" {
  command = plan
  variables { admin_ipv4 = "not-an-ip" }
  expect_failures = [var.admin_ipv4]
}

run "reject_ipv6_administrator_address" {
  command = plan
  variables { admin_ipv4 = "2001:db8::1" }
  expect_failures = [var.admin_ipv4]
}
