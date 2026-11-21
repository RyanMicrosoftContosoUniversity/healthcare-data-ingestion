locals {
  tags = { project = "healthcare-data-ingestion", environment = "demo" }
  sources = {
    clarity  = { server = "healthcare-data-ingestion-clarity-sql", database = "Clarity" }
    caboodle = { server = "healthcare-data-ingestion-caboodle-sql", database = "Caboodle" }
  }
}

data "azurerm_resource_group" "demo" {
  name = "healthcare-data-ingestion-rg"
}

resource "azurerm_user_assigned_identity" "machine" {
  for_each            = toset(["generator", "source-reader", "control", "diagnostics"])
  name                = "hc-ingestion-${each.key}"
  resource_group_name = data.azurerm_resource_group.demo.name
  location            = var.location
  tags                = local.tags
}

resource "azurerm_mssql_server" "source" {
  for_each                      = local.sources
  name                          = each.value.server
  resource_group_name           = data.azurerm_resource_group.demo.name
  location                      = var.location
  version                       = "12.0"
  minimum_tls_version           = "1.2"
  public_network_access_enabled = true
  azuread_administrator {
    login_username              = var.sql_admin_name
    object_id                   = var.sql_admin_object_id
    tenant_id                   = var.tenant_id
    azuread_authentication_only = true
  }
  tags = local.tags
}

resource "azurerm_mssql_database" "source" {
  for_each    = local.sources
  name        = each.value.database
  server_id   = azurerm_mssql_server.source[each.key].id
  sku_name    = "S0"
  max_size_gb = 2
  tags        = local.tags
  lifecycle { prevent_destroy = true }
}

resource "azurerm_mssql_firewall_rule" "azure_services" {
  for_each         = local.sources
  name             = "ApprovedAzureServicesException"
  server_id        = azurerm_mssql_server.source[each.key].id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_mssql_firewall_rule" "administrator" {
  for_each         = local.sources
  name             = "ApprovedAdministrator"
  server_id        = azurerm_mssql_server.source[each.key].id
  start_ip_address = var.admin_ipv4
  end_ip_address   = var.admin_ipv4
}

resource "azurerm_storage_account" "generator" {
  name                            = "hcingestionstore"
  resource_group_name             = data.azurerm_resource_group.demo.name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  access_tier                     = "Hot"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false
  public_network_access_enabled   = true
  tags                            = merge(local.tags, { cost_component = "generator" })
  lifecycle { prevent_destroy = true }
}

resource "azurerm_storage_container" "generator" {
  for_each              = toset(["population", "identities", "exports", "checkpoints"])
  name                  = each.key
  storage_account_id    = azurerm_storage_account.generator.id
  container_access_type = "private"
}

resource "azurerm_container_registry" "generator" {
  name                = "hcingestionacr"
  resource_group_name = data.azurerm_resource_group.demo.name
  location            = var.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = merge(local.tags, { cost_component = "generator" })
  lifecycle { prevent_destroy = true }
}

resource "azurerm_role_assignment" "generator_blob" {
  for_each             = azurerm_storage_container.generator
  scope                = each.value.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.machine["generator"].principal_id
}

resource "azurerm_role_assignment" "generator_registry" {
  scope                = azurerm_container_registry.generator.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.machine["generator"].principal_id
}

resource "azurerm_log_analytics_workspace" "operations" {
  name                = "hc-ingestion-operations"
  location            = var.location
  resource_group_name = data.azurerm_resource_group.demo.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.1
  tags                = local.tags
}

resource "azurerm_container_app_environment" "generator" {
  name                       = "hc-ingestion-generator-environment"
  resource_group_name        = data.azurerm_resource_group.demo.name
  location                   = var.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.operations.id
  tags                       = merge(local.tags, { cost_component = "generator" })
}

resource "azurerm_container_app_job" "generator" {
  count                        = var.provision_generator ? 1 : 0
  name                         = "hc-ingestion-generator"
  location                     = var.location
  resource_group_name          = data.azurerm_resource_group.demo.name
  container_app_environment_id = azurerm_container_app_environment.generator.id
  replica_timeout_in_seconds   = 2700
  replica_retry_limit          = 1
  dynamic "schedule_trigger_config" {
    for_each = var.activate_generator ? [true] : []
    content {
      cron_expression          = "0 12 * * *"
      parallelism              = 1
      replica_completion_count = 1
    }
  }
  dynamic "manual_trigger_config" {
    for_each = var.activate_generator ? [] : [true]
    content {
      parallelism              = 1
      replica_completion_count = 1
    }
  }
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.machine["generator"].id]
  }
  registry {
    server   = azurerm_container_registry.generator.login_server
    identity = azurerm_user_assigned_identity.machine["generator"].id
  }
  template {
    container {
      name   = "generator"
      image  = var.generator_image
      cpu    = 2
      memory = "4Gi"
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.machine["generator"].client_id
      }
      env {
        name  = "GENERATOR_STORAGE_ACCOUNT"
        value = azurerm_storage_account.generator.name
      }
      env {
        name  = "GENERATOR_STATE_CONTAINER"
        value = "population"
      }
      env {
        name  = "GENERATOR_EXPORT_CONTAINER"
        value = "exports"
      }
      env {
        name  = "GENERATOR_MANIFEST_CONTAINER"
        value = "checkpoints"
      }
      env {
        name  = "CLARITY_SQL_SERVER"
        value = azurerm_mssql_server.source["clarity"].fully_qualified_domain_name
      }
      env {
        name  = "CABOODLE_SQL_SERVER"
        value = azurerm_mssql_server.source["caboodle"].fully_qualified_domain_name
      }
      env {
        name  = "CLARITY_SQL_DATABASE"
        value = "Clarity"
      }
      env {
        name  = "CABOODLE_SQL_DATABASE"
        value = "Caboodle"
      }
      env {
        name  = "GENERATOR_TIMEOUT_SECONDS"
        value = "2700"
      }
    }
  }
  tags       = merge(local.tags, { cost_component = "generator" })
  depends_on = [azurerm_role_assignment.generator_registry, azurerm_role_assignment.generator_blob]
  lifecycle {
    precondition {
      condition     = var.generator_image != null
      error_message = "Publish an immutable registry image before provisioning the generator job."
    }
  }
}

resource "fabric_workspace" "metadata" {
  display_name = "healthcare-data-ingestion-metadata"
  capacity_id  = var.capacity_id
  identity     = { type = "SystemAssigned" }
  lifecycle { prevent_destroy = true }
}

resource "fabric_workspace" "data" {
  display_name = "healthcare-data-ingestion-data"
  capacity_id  = var.capacity_id
  identity     = { type = "SystemAssigned" }
  lifecycle { prevent_destroy = true }
}

resource "fabric_sql_database" "metadata" {
  display_name = "healthcare-data-ingestion-metadata-db"
  workspace_id = fabric_workspace.metadata.id
  lifecycle { prevent_destroy = true }
}

resource "fabric_lakehouse" "data" {
  for_each      = toset(["bronze", "silver"])
  display_name  = "healthcare_data_ingestion_${each.key}"
  workspace_id  = fabric_workspace.data.id
  configuration = { enable_schemas = true }
  lifecycle { prevent_destroy = true }
}

resource "fabric_environment" "release" {
  for_each     = var.retained_framework_versions
  display_name = "hc-ingestion-environment-${each.key}"
  workspace_id = fabric_workspace.data.id
  lifecycle { prevent_destroy = true }
}

resource "fabric_spark_environment_settings" "release" {
  for_each           = fabric_environment.release
  workspace_id       = fabric_workspace.data.id
  environment_id     = each.value.id
  publication_status = "Published"
  runtime_version    = "2.0"
  spark_properties   = { "spark.sql.session.timeZone" = "UTC" }
}

resource "fabric_apache_airflow_job" "orchestration" {
  display_name = "hc-ingestion-orchestration"
  workspace_id = fabric_workspace.data.id
}

resource "azurerm_role_assignment" "fabric_checkpoint_reader" {
  for_each             = azurerm_storage_container.generator
  scope                = each.value.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = fabric_workspace.data.identity.service_principal_id
}
