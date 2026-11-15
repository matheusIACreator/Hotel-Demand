locals {
  tags = { project = "hotelml", environment = "dev", managed_by = "terraform" }
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${var.name}"
  location = coalesce(var.resource_group_location, var.location)
  tags     = local.tags
}

resource "azurerm_container_registry" "main" {
  name                = var.registry_name
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.tags
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "logs-${var.name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.1
  tags                = local.tags
}

resource "azurerm_container_app_environment" "main" {
  name                       = "env-${var.name}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = var.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags

  # A Azure cria este perfil por omissão; declará-lo evita drift no segundo apply.
  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
    minimum_count         = 0
    maximum_count         = 0
  }
}

resource "azurerm_user_assigned_identity" "api" {
  name                = "id-${var.name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  tags                = local.tags
}

resource "azurerm_role_assignment" "pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}

resource "azurerm_container_app" "api" {
  count                        = var.image == "" ? 0 : 1
  name                         = "api-${var.name}"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  workload_profile_name        = "Consumption"
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.api.id]
  }
  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.api.id
  }
  template {
    min_replicas = 0
    max_replicas = 1
    container {
      name   = "api"
      image  = var.image
      cpu    = 0.5
      memory = "1Gi"

      # Verificar a cada 2 s encurta a espera entre o modelo carregar e a réplica ser aceita.
      # 75 falhas mantêm os mesmos 150 s de tolerância para o arranque.
      startup_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health/ready"
        interval_seconds        = 2
        failure_count_threshold = 75
        timeout                 = 2
      }
      liveness_probe {
        transport        = "HTTP"
        port             = 8000
        path             = "/health/live"
        interval_seconds = 30
        timeout          = 3
      }
      # O provider exige 3 sucessos seguidos por omissão; com intervalo de 10 s, a réplica já
      # pronta ficava 20 a 30 s sem receber o pedido que a acordou (ADR 0013). O modelo carrega
      # antes de a porta abrir, por isso um único sucesso basta. A tolerância a falhas mantém
      # os 30 s anteriores (10 x 3 s).
      readiness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health/ready"
        interval_seconds        = 3
        success_count_threshold = 1
        failure_count_threshold = 10
        timeout                 = 3
      }
    }
    http_scale_rule {
      name                = "http"
      concurrent_requests = "10"
    }
  }
  ingress {
    external_enabled           = true
    allow_insecure_connections = false
    target_port                = 8000
    transport                  = "http"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  # Após bootstrap, CD controla somente a imagem; Terraform mantém a restante configuração.
  lifecycle {
    ignore_changes = [template[0].container[0].image]
    precondition {
      condition     = startswith(var.image, "${azurerm_container_registry.main.login_server}/")
      error_message = "Use uma imagem do ACR deste projeto."
    }
  }
  depends_on = [azurerm_role_assignment.pull]
}

resource "azurerm_consumption_budget_resource_group" "main" {
  name              = "budget-${var.name}"
  resource_group_id = azurerm_resource_group.main.id
  amount            = var.budget_amount
  time_grain        = "Monthly"
  time_period {
    start_date = var.budget_start_date
  }
  dynamic "notification" {
    for_each = toset([50, 80, 100])
    content {
      enabled        = true
      threshold      = notification.value
      operator       = "GreaterThanOrEqualTo"
      contact_emails = [var.budget_email]
    }
  }
}
