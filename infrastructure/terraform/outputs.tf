output "source_servers" {
  value = { for name, server in azurerm_mssql_server.source : name => server.fully_qualified_domain_name }
}

output "generator_identity" {
  value = azurerm_user_assigned_identity.machine["generator"]
}

output "metadata_database" {
  value = fabric_sql_database.metadata.properties
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

output "lakehouses" {
  value = { for name, lakehouse in fabric_lakehouse.data : name => lakehouse.id }
}

output "release_environment_id" {
  value = fabric_environment.release[var.framework_version].id
}

output "airflow_item_id" {
  value = fabric_apache_airflow_job.orchestration.id
}
