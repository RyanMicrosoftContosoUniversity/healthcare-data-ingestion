variable "runtime_principal_object_ids" {
  type        = map(string)
  description = "Real certificate-backed SP object IDs: control, source-reader, diagnostics, orchestrator."
  validation {
    condition = alltrue([
      for role in ["control", "source-reader", "diagnostics", "orchestrator"] :
      can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.runtime_principal_object_ids[role]))
    ])
    error_message = "Supply all four reviewed actual service principal object IDs."
  }
}

resource "azurerm_storage_container" "framework_recovery" {
  name                  = "framework-recovery"
  storage_account_id    = azurerm_storage_account.generator.id
  container_access_type = "private"
  lifecycle { prevent_destroy = true }
}

resource "azurerm_role_assignment" "framework_recovery" {
  for_each             = toset(["control", "diagnostics"])
  scope                = azurerm_storage_container.framework_recovery.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.runtime_principal_object_ids[each.key]
}

resource "azurerm_role_assignment" "runtime_generator_reader" {
  for_each             = azurerm_storage_container.generator
  scope                = each.value.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = var.runtime_principal_object_ids["source-reader"]
}

resource "azurerm_role_assignment" "runtime_log_publisher" {
  scope                = azurerm_monitor_data_collection_rule.events.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = var.runtime_principal_object_ids["diagnostics"]
}
