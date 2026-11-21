variable "release_bundle_directories" {
  type        = map(string)
  description = "Absolute immutable prepared bundle paths, keyed by retained framework semver."
}

locals {
  notebooks = merge([
    for version in var.retained_framework_versions : {
      for workflow, stage in {
        clarity_bronze  = "bronze"
        caboodle_bronze = "bronze"
        patient_silver  = "silver"
        } : "${version}-${workflow}" => {
        version  = version
        workflow = workflow
        stage    = stage
        source   = stage == "bronze" ? "bronze.ipynb" : "patient-silver.ipynb"
      }
    }
  ]...)
}

resource "fabric_notebook" "worker" {
  for_each                  = local.notebooks
  display_name              = "hc-${each.value.workflow}-${each.value.version}"
  workspace_id              = fabric_workspace.data.id
  format                    = "ipynb"
  definition_update_enabled = false
  definition = {
    "notebook-content.ipynb" = {
      source = "${var.release_bundle_directories[each.value.version]}/${each.value.source}"
      tokens = {
        EnvironmentId = fabric_environment.release[each.value.version].id
        WorkspaceId   = fabric_workspace.data.id
        LakehouseId   = fabric_lakehouse.data[each.value.stage].id
        LakehouseName = fabric_lakehouse.data[each.value.stage].display_name
      }
    }
  }
  lifecycle { prevent_destroy = true }
}

output "release_notebooks" {
  value = { for key, notebook in fabric_notebook.worker : key => notebook.id }
}
