locals {
  log_columns = [
    { name = "TimeGenerated", type = "datetime" },
    { name = "Level", type = "string" },
    { name = "Event", type = "string" },
    { name = "ExceptionType", type = "string" },
    { name = "Context", type = "dynamic" },
  ]
  alert_events = toset([
    "RunFailed", "FreshnessMissed", "DeadlineMissed", "MemoryPressure",
    "DurationRegression", "TelemetryGap", "CleanupFailed",
  ])
}

resource "azapi_resource" "event_table" {
  type      = "Microsoft.OperationalInsights/workspaces/tables@2022-10-01"
  name      = "HcIngestion_CL"
  parent_id = azurerm_log_analytics_workspace.operations.id
  body = {
    properties = {
      schema               = { name = "HcIngestion_CL", columns = local.log_columns }
      plan                 = "Analytics"
      retentionInDays      = 30
      totalRetentionInDays = 30
    }
  }
}

resource "azurerm_monitor_data_collection_endpoint" "events" {
  name                = "hc-ingestion-events"
  location            = var.location
  resource_group_name = data.azurerm_resource_group.demo.name
  tags                = local.tags
}

resource "azurerm_monitor_data_collection_rule" "events" {
  name                        = "hc-ingestion-events"
  location                    = var.location
  resource_group_name         = data.azurerm_resource_group.demo.name
  data_collection_endpoint_id = azurerm_monitor_data_collection_endpoint.events.id
  destinations {
    log_analytics {
      name                  = "operations"
      workspace_resource_id = azurerm_log_analytics_workspace.operations.id
    }
  }
  stream_declaration {
    stream_name = "Custom-HcIngestion"
    dynamic "column" {
      for_each = local.log_columns
      content {
        name = column.value.name
        type = column.value.type
      }
    }
  }
  data_flow {
    streams       = ["Custom-HcIngestion"]
    destinations  = ["operations"]
    output_stream = "Custom-HcIngestion_CL"
    transform_kql = "source"
  }
  tags       = local.tags
  depends_on = [azapi_resource.event_table]
}

resource "azurerm_role_assignment" "event_publishers" {
  for_each             = toset(["generator", "diagnostics"])
  scope                = azurerm_monitor_data_collection_rule.events.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = azurerm_user_assigned_identity.machine[each.key].principal_id
}

resource "azurerm_role_assignment" "fabric_event_publisher" {
  count                = var.fabric_workspace_identity_object_id == null ? 0 : 1
  scope                = azurerm_monitor_data_collection_rule.events.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = var.fabric_workspace_identity_object_id
}

resource "azurerm_monitor_action_group" "email" {
  name                = "hc-ingestion-email"
  resource_group_name = data.azurerm_resource_group.demo.name
  short_name          = "hcingestion"
  email_receiver {
    name                    = "confirmed-owner"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }
  tags = local.tags
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "events" {
  for_each             = local.alert_events
  name                 = "hc-ingestion-${each.key}"
  resource_group_name  = data.azurerm_resource_group.demo.name
  location             = var.location
  evaluation_frequency = "PT5M"
  window_duration      = each.key == "TelemetryGap" ? "PT15M" : "PT5M"
  scopes               = [azurerm_log_analytics_workspace.operations.id]
  severity             = each.key == "RunFailed" ? 1 : 2
  enabled              = var.activate_alerts
  criteria {
    query                   = each.key == "TelemetryGap" ? "union (HcIngestion_CL | where Event == 'TelemetryGap'), (HcIngestion_CL | where Event == 'ControlHeartbeat' | summarize Last=max(TimeGenerated) | where isnull(Last) or Last < ago(15m) | extend Event='TelemetryGap')" : "HcIngestion_CL | where Event == '${each.key}' | summarize arg_max(TimeGenerated, *) by tostring(Context.event_id)"
    time_aggregation_method = "Count"
    operator                = "GreaterThan"
    threshold               = 0
    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }

  }
  action { action_groups = [azurerm_monitor_action_group.email.id] }
  tags       = local.tags
  depends_on = [azapi_resource.event_table]
}

output "log_ingestion" {
  value = {
    endpoint = azurerm_monitor_data_collection_endpoint.events.logs_ingestion_endpoint
    rule_id  = azurerm_monitor_data_collection_rule.events.immutable_id
    stream   = "Custom-HcIngestion"
  }
}
