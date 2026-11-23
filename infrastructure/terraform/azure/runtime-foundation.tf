variable "provision_runtime_principals" {
  type        = bool
  default     = false
  description = "Create the four new certificate-backed runtime app/SP identities instead of using external object IDs."
}

variable "deployment_principal_object_id" {
  type        = string
  default     = "cb05819f-8465-46f7-a696-b5ebdb91b10c"
  description = "Actual fabric-sc service principal; owns runtime apps/SPs and manages vault certificates."
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.deployment_principal_object_id))
    error_message = "Supply the actual deployment service-principal object ID."
  }
}

locals {
  runtime_roles = toset(["control", "source-reader", "diagnostics", "orchestrator"])
  runtime_principal_object_ids = var.provision_runtime_principals ? {
    for role, principal in azuread_service_principal.runtime : role => principal.object_id
  } : var.runtime_principal_object_ids
}

resource "azurerm_key_vault" "runtime" {
  name                       = "hcingestion-runtime-kv"
  resource_group_name        = data.azurerm_resource_group.demo.name
  location                   = var.location
  tenant_id                  = var.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = true
  soft_delete_retention_days = 90
  tags                       = local.tags
  lifecycle { prevent_destroy = true }
}

resource "azurerm_role_assignment" "runtime_certificates" {
  scope                = azurerm_key_vault.runtime.id
  role_definition_name = "Key Vault Certificates Officer"
  principal_id         = var.deployment_principal_object_id
}

resource "azuread_application" "runtime" {
  for_each                = var.provision_runtime_principals ? local.runtime_roles : toset([])
  display_name            = "hc-ingestion-runtime-${each.key}"
  prevent_duplicate_names = true
  sign_in_audience        = "AzureADMyOrg"
  owners                  = [var.deployment_principal_object_id]
  lifecycle { prevent_destroy = true }
}

resource "azuread_service_principal" "runtime" {
  for_each  = azuread_application.runtime
  client_id = each.value.client_id
  owners    = [var.deployment_principal_object_id]
  lifecycle { prevent_destroy = true }
}

resource "azurerm_key_vault_certificate" "runtime" {
  for_each     = azuread_application.runtime
  name         = "${each.key}-v1"
  key_vault_id = azurerm_key_vault.runtime.id
  certificate_policy {
    issuer_parameters { name = "Self" }
    key_properties {
      exportable = true
      key_size   = 3072
      key_type   = "RSA"
      reuse_key  = false
    }
    secret_properties { content_type = "application/x-pkcs12" }
    x509_certificate_properties {
      extended_key_usage = ["1.3.6.1.5.5.7.3.2"]
      key_usage          = ["digitalSignature"]
      subject            = "CN=${each.value.display_name}"
      validity_in_months = 12
    }
  }
  depends_on = [azurerm_role_assignment.runtime_certificates]
  lifecycle { prevent_destroy = true }
}

resource "azuread_application_certificate" "runtime" {
  for_each       = azurerm_key_vault_certificate.runtime
  application_id = azuread_application.runtime[each.key].id
  type           = "AsymmetricX509Cert"
  encoding       = "hex"
  value          = each.value.certificate_data
  start_date     = each.value.certificate_attribute[0].not_before
  end_date       = each.value.certificate_attribute[0].expires
  lifecycle { prevent_destroy = true }
}
