locals {
  telemetry_query = <<-KQL
    ContainerAppConsoleLogs_CL
    | where ContainerAppName_s == ${jsonencode("api-${var.name}")}
    | extend telemetry = parse_json(Log_s)
    | where toint(telemetry.schema_version) == 1
  KQL
  monitoring_queries = {
    errors  = <<-KQL
      ${local.telemetry_query}
      | where tostring(telemetry.event) == "http_request"
      | where tostring(telemetry.route) == "/predict" and tostring(telemetry.method) == "POST"
      | summarize requests=count(), errors=countif(toint(telemetry.status_code) >= 500) by RevisionName_s
      | extend error_percent = 100.0 * errors / requests
      | where requests >= ${var.monitoring_min_requests} and errors >= 3 and error_percent >= ${var.monitoring_error_percent}
    KQL
    latency = <<-KQL
      ${local.telemetry_query}
      | where tostring(telemetry.event) == "http_request"
      | where tostring(telemetry.route) == "/predict" and tostring(telemetry.method) == "POST"
      | where toint(telemetry.status_code) between (200 .. 299)
      | summarize requests=count(), p95_ms=percentile(todouble(telemetry.duration_ms), 95) by RevisionName_s
      | where requests >= ${var.monitoring_min_requests} and p95_ms > ${var.monitoring_latency_ms}
    KQL
    startup = <<-KQL
      ${local.telemetry_query}
      | where tostring(telemetry.event) == "model_load_failed"
      | project TimeGenerated, RevisionName_s
    KQL
  }
  monitoring_descriptions = {
    errors  = "Previsões com 5xx: pelo menos 3 falhas, volume mínimo e taxa acima do limite em 15 minutos."
    latency = "P95 de previsões 2xx dentro da API acima do limite, com volume mínimo em 15 minutos. Não mede espera por réplica."
    startup = "Falha no carregamento do modelo; ausência de tráfego e escala a zero não disparam este alerta."
  }
}

resource "azurerm_monitor_action_group" "api" {
  count               = var.monitoring_enabled ? 1 : 0
  name                = "alerts-${var.name}"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "hotelml"
  tags                = local.tags

  email_receiver {
    name                    = "operacao"
    email_address           = var.budget_email
    use_common_alert_schema = true
  }
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "api" {
  for_each = var.monitoring_enabled ? local.monitoring_queries : {}

  name                    = "api-${var.name}-${each.key}"
  display_name            = "hotelml: ${each.key}"
  resource_group_name     = azurerm_resource_group.main.name
  location                = var.location
  scopes                  = [azurerm_log_analytics_workspace.main.id]
  description             = local.monitoring_descriptions[each.key]
  severity                = each.key == "latency" ? 2 : 1
  evaluation_frequency    = "PT5M"
  window_duration         = "PT15M"
  enabled                 = true
  auto_mitigation_enabled = true
  tags                    = local.tags

  criteria {
    query                   = each.value
    time_aggregation_method = "Count"
    operator                = "GreaterThan"
    threshold               = 0
    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }
  action {
    action_groups = [azurerm_monitor_action_group.api[0].id]
  }
}
