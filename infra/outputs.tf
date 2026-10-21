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
