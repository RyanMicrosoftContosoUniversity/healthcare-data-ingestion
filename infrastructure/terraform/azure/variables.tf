variable "subscription_id" {
  type    = string
  default = "910ebf13-1058-405d-b6cf-eda03e5288d1"
}

variable "tenant_id" {
  type    = string
  default = "35acf02c-4b87-4ae6-9221-ff5cafd430b4"
}

variable "sql_admin_object_id" {
  type        = string
  description = "Verified Entra administrator object; no SQL authentication credentials."
  default     = "c65f2c4b-7fe6-4274-b8c9-2bcfbb6d784b"
}

variable "sql_admin_name" {
  type    = string
  default = "healthcare-demo-administrator"
}

variable "admin_ipv4" {
  type        = string
  description = "Approved human client's public IPv4 address, required before plan."
  validation {
    condition     = can(cidrhost("${var.admin_ipv4}/32", 0))
    error_message = "Supply an explicit IPv4 address."
  }
}

variable "generator_image" {
  type        = string
  default     = null
  description = "Immutable hcingestionacr image reference including @sha256 digest."
  validation {
    condition     = var.generator_image == null || can(regex("^hcingestionacr\\.azurecr\\.io/.+@sha256:[0-9a-f]{64}$", var.generator_image))
    error_message = "Use an immutable approved-registry image digest."
  }
}

variable "provision_generator" {
  type        = bool
  default     = false
  description = "Provision only after the registry image exists; initial foundation apply creates no job."
}

variable "activate_generator" {
  type        = bool
  default     = false
  description = "Daily schedule activation requires verified SQL schemas, grants and runtime acceptance."
}

variable "alert_email" {
  type        = string
  description = "Confirmed Outlook/email recipient. Required before alert activation."
  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "Supply the confirmed email address."
  }

}

variable "activate_alerts" {
  type        = bool
  default     = false
  description = "Enable only after reviewed deployment, real telemetry and email delivery acceptance."
}

variable "location" {
  type    = string
  default = "eastus"
  validation {
    condition     = var.location == "eastus"
    error_message = "Changing the approved Azure region requires a revised costed plan."
  }

}

variable "fabric_workspace_identity_object_id" {
  type        = string
  default     = null
  description = "Actual Fabric data-workspace identity output; omit on foundation apply, supply after Fabric creation for Azure-scoped grants."
  validation {
    condition     = var.fabric_workspace_identity_object_id == null || can(regex("^[0-9a-fA-F-]{36}$", var.fabric_workspace_identity_object_id))
    error_message = "Supply the actual Fabric data-workspace service-principal object ID."
  }
}
