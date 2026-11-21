variable "budget_start_date" {
  type        = string
  description = "First day of the reviewed deployment month, UTC (YYYY-MM-01T00:00:00Z)."
  validation {
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-01T00:00:00Z$", var.budget_start_date))
    error_message = "Budget start must be the first day of a month in UTC."
  }
}

resource "azurerm_consumption_budget_resource_group" "generator" {
  name              = "hc-ingestion-generator"
  resource_group_id = data.azurerm_resource_group.demo.id
  amount            = 10
  time_grain        = "Monthly"
  time_period { start_date = var.budget_start_date }
  filter {
    tag {
      name   = "cost_component"
      values = ["generator"]
    }
  }
  dynamic "notification" {
    for_each = toset([80, 100])
    content {
      enabled        = true
      threshold      = notification.value
      operator       = "GreaterThanOrEqualTo"
      threshold_type = "Actual"
      contact_emails = [var.alert_email]
    }
  }
}
