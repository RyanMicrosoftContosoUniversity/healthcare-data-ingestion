output "source_servers" {
  value = { for name, server in azurerm_mssql_server.source : name => server.fully_qualified_domain_name }
}

output "generator_identity" {
  value = azurerm_user_assigned_identity.machine["generator"]
}

output "storage_account_name" {
  value = azurerm_storage_account.generator.name
}
