terraform {
  required_version = ">= 1.13.4, < 2.0.0"
  required_providers {
    fabric = {
      source  = "microsoft/fabric"
      version = "= 1.15.1"
    }
  }
  backend "azurerm" {}
}

provider "fabric" {}

variable "capacity_id" {
  type    = string
  default = "ad343e36-f335-4ba3-b261-b739f7e950b0"
}

variable "runtime_principal_object_ids" {
  type        = map(string)
  description = "Actual control and orchestrator Entra service-principal object IDs; Azure grants are managed separately."
  validation {
    condition = alltrue([
      for role in ["control", "orchestrator"] :
      can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.runtime_principal_object_ids[role]))
    ])
    error_message = "Supply the actual control and orchestrator principal object IDs."
  }
}

variable "workspace_access" {
  type = map(object({
    workspace      = string
    principal_id   = string
    principal_type = string
    role           = string
  }))
  default     = {}
  description = "Additional reviewed existing Entra users/groups/SPs; this assigns Fabric access, not Entra account creation."
  validation {
    condition = alltrue([
      for assignment in values(var.workspace_access) :
      contains(["data", "metadata"], assignment.workspace) &&
      contains(["User", "Group", "ServicePrincipal"], assignment.principal_type) &&
      contains(["Admin", "Member", "Contributor", "Viewer"], assignment.role) &&
      can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", assignment.principal_id))
    ])
    error_message = "Use an approved data/metadata workspace, valid principal type/GUID and Fabric role."
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

resource "fabric_workspace_role_assignment" "runtime_data" {
  for_each     = toset(["control", "orchestrator"])
  workspace_id = fabric_workspace.data.id
  role         = "Contributor"
  principal = {
    id   = var.runtime_principal_object_ids[each.key]
    type = "ServicePrincipal"
  }
}

resource "fabric_workspace_role_assignment" "runtime_metadata" {
  for_each     = toset(["control", "orchestrator"])
  workspace_id = fabric_workspace.metadata.id
  role         = "Viewer"
  principal = {
    id   = var.runtime_principal_object_ids[each.key]
    type = "ServicePrincipal"
  }
}

resource "fabric_workspace_role_assignment" "access" {
  for_each     = var.workspace_access
  workspace_id = each.value.workspace == "data" ? fabric_workspace.data.id : fabric_workspace.metadata.id
  role         = each.value.role
  principal = {
    id   = each.value.principal_id
    type = each.value.principal_type
  }
}

output "fabric_data_workspace_id" {
  value = fabric_workspace.data.id
}

output "fabric_metadata_workspace_id" {
  value = fabric_workspace.metadata.id
}

output "fabric_data_identity_object_id" {
  value = fabric_workspace.data.identity.service_principal_id
}

output "metadata_database" {
  value = fabric_sql_database.metadata.properties
}

output "lakehouses" {
  value = { for name, lakehouse in fabric_lakehouse.data : name => lakehouse.id }
}
