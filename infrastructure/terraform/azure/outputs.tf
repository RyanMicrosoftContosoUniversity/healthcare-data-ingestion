output "source_servers" {
  value = { for name, server in azurerm_mssql_server.source : name => server.fully_qualified_domain_name }
}

output "generator_identity" {
  value = azurerm_user_assigned_identity.machine["generator"]
}

output "storage_account_name" {
  value = azurerm_storage_account.generator.name
}

output "runtime_principal_object_ids" {
  value = local.runtime_principal_object_ids
}

output "runtime_key_vault_uri" {
  value = azurerm_key_vault.runtime.vault_uri
}

output "runtime_identities" {
  value = {
    for role, application in azuread_application.runtime : role => {
      tenant_id             = var.tenant_id
      client_id             = application.client_id
      principal_object_id   = azuread_service_principal.runtime[role].object_id
      certificate_id        = azurerm_key_vault_certificate.runtime[role].id
      certificate_secret_id = azurerm_key_vault_certificate.runtime[role].secret_id
    }
  }
}
