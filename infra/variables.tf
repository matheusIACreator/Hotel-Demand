variable "subscription_id" {
  type        = string
  description = "ID da subscrição Azure."
}

variable "name" {
  type        = string
  default     = "hotelml-dev"
  description = "Prefixo dos recursos."
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,19}$", var.name))
    error_message = "Use 3 a 20 caracteres: letras minúsculas, números e hífen."
  }
}

variable "location" {
  type    = string
  default = "northeurope"
}

variable "resource_group_location" {
  type        = string
  default     = null
  description = "Região dos metadados do grupo existente; por omissão usa location."
}

variable "registry_name" {
  type        = string
  description = "Nome globalmente único do ACR (5 a 50 letras minúsculas/números)."
  validation {
    condition     = can(regex("^[a-z0-9]{5,50}$", var.registry_name))
    error_message = "Nome do ACR inválido."
  }
}

variable "image" {
  type        = string
  default     = ""
  description = "Imagem hotelml no ACR; vazio cria apenas a infraestrutura de base."
}

variable "budget_amount" {
  type        = number
  default     = 20
  description = "Orçamento mensal na moeda de faturação da subscrição."
  validation {
    condition     = var.budget_amount > 0
    error_message = "O orçamento deve ser positivo."
  }
}

variable "budget_start_date" {
  type        = string
  description = "Primeiro dia do mês da criação, por exemplo 2026-10-01T00:00:00Z."
  validation {
    condition     = can(regex("^\\d{4}-\\d{2}-01T00:00:00Z$", var.budget_start_date))
    error_message = "Informe o primeiro dia do mês em UTC."
  }
}

variable "budget_email" {
  type        = string
  description = "Destinatário dos alertas de orçamento."
  validation {
    condition     = can(regex("^[^@ ]+@[^@ ]+\\.[^@ ]+$", var.budget_email))
    error_message = "Informe um email válido."
  }
}

variable "monitoring_enabled" {
  type        = bool
  default     = false
  description = "Ativa três alertas de logs e email operacional; regras e ingestão podem gerar cobrança."
}

variable "monitoring_min_requests" {
  type        = number
  default     = 20
  description = "Mínimo de previsões por revisão em 15 minutos para avaliar erros e latência."
  validation {
    condition     = var.monitoring_min_requests >= 3 && floor(var.monitoring_min_requests) == var.monitoring_min_requests
    error_message = "O volume mínimo deve ser um inteiro maior ou igual a 3."
  }
}

variable "monitoring_error_percent" {
  type        = number
  default     = 10
  description = "Percentual mínimo de respostas 5xx; exige também pelo menos três falhas."
  validation {
    condition     = var.monitoring_error_percent > 0 && var.monitoring_error_percent <= 100
    error_message = "Informe um percentual entre 0 (exclusivo) e 100."
  }
}

variable "monitoring_latency_ms" {
  type        = number
  default     = 2000
  description = "Limite inicial do P95 das previsões 2xx dentro da API, em milissegundos."
  validation {
    condition     = var.monitoring_latency_ms > 0
    error_message = "O limite de latência deve ser positivo."
  }
}
