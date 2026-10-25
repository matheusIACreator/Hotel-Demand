output "resource_group" {
  value = azurerm_resource_group.main.name
}

output "registry_name" {
  value = azurerm_container_registry.main.name
}

output "registry_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "app_name" {
  value = "api-${var.name}"
}

output "api_url" {
  value = try("https://${azurerm_container_app.api[0].ingress[0].fqdn}", null)
}

output "monitoring_queries" {
  description = "Consultas KQL dos alertas; execute na janela de 15 minutos do workspace."
  value       = local.monitoring_queries
}

output "monitoring_alert_ids" {
  value = { for name, rule in azurerm_monitor_scheduled_query_rules_alert_v2.api : name => rule.id }
}
