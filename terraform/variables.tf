##############################################################################
# variables.tf — all input variables with descriptions and defaults
##############################################################################

# ── Project metadata ──────────────────────────────────────────────────────────

variable "project" {
  description = "Short project name — used as prefix for all resource names."
  type        = string
  default     = "agentic-react"
}

variable "environment" {
  description = "Deployment environment: dev | staging | prod"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "resource_group_name" {
  description = "Name of the Azure Resource Group."
  type        = string
  default     = "rg-agentic-react-prod"
}

variable "location" {
  description = "Azure region for all resources (except Azure OpenAI — see openai_location)."
  type        = string
  default     = "westeurope"
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default = {
    project     = "agentic-react"
    environment = "prod"
    managed_by  = "terraform"
  }
}

# ── Azure OpenAI ──────────────────────────────────────────────────────────────

variable "openai_location" {
  description = <<EOT
Azure region where Azure OpenAI is deployed.
GPT-4o is available in: eastus, eastus2, swedencentral, westus.
This may differ from var.location — the Private Endpoint bridges both.
EOT
  type        = string
  default     = "eastus"
}

variable "openai_api_key" {
  description = "Azure OpenAI API key — stored in Key Vault, never in state plain text."
  type        = string
  sensitive   = true
}

variable "openai_capacity_tpm" {
  description = "GPT-4o deployment capacity in thousands-of-tokens-per-minute (TPM)."
  type        = number
  default     = 1
}

variable "openai_model" {
  description = <<EOT
Azure OpenAI chat model to deploy.
- "gpt-4o"      → higher quality, requires quota approval (https://aka.ms/oai/quotaincrease)
- "gpt-4o-mini" → available on most new subscriptions with minimal quota
EOT
  type        = string
  default     = "gpt-4o-mini"
}

variable "deploy_openai_models" {
  description = <<EOT
Set to false to skip creating the Azure OpenAI model deployments.
Useful when the subscription has quota=0 for the selected model.
The Cognitive Account itself is still created; request quota increase at
https://aka.ms/oai/quotaincrease, then set this to true and re-apply.
EOT
  type        = bool
  default     = true
}

variable "openai_deployment_type" {
  description = <<EOT
Azure OpenAI deployment scale type.
- "Standard"       → available on all subscriptions, lower throughput
- "GlobalStandard" → higher throughput, requires pre-approved quota
To check/request quota: https://aka.ms/oai/quotaincrease
EOT
  type        = string
  default     = "Standard"

  validation {
    condition     = contains(["Standard", "GlobalStandard"], var.openai_deployment_type)
    error_message = "openai_deployment_type must be 'Standard' or 'GlobalStandard'."
  }
}

variable "terraform_ip" {
  description = <<EOT
Your public egress IP address (the machine running terraform apply).
Added to Key Vault ip_rules so Terraform can write secrets during provisioning.
Get it with: (Invoke-WebRequest https://api.ipify.org -UseBasicParsing).Content
EOT
  type        = string
  default     = "38.190.72.74"
}

# ── Azure SQL (SQL Server) ────────────────────────────────────────────────────

variable "mssql_admin_user" {
  description = "Administrator login for Azure SQL Server."
  type        = string
  default     = "reactadmin"
}

variable "mssql_password" {
  description = "Administrator password for Azure SQL Server — stored in Key Vault."
  type        = string
  sensitive   = true
}

variable "mssql_database" {
  description = "Name of the application database."
  type        = string
  default     = "react_db"
}

variable "mssql_sku" {
  description = <<EOT
SKU for Azure SQL Database.
- "Basic"       → cheapest, 5 DTUs, dev/test only
- "S1"          → 20 DTUs, light production
- "GP_S_Gen5_1" → serverless, auto-pause, recommended for demos
EOT
  type        = string
  default     = "Basic"
}

# ── Application security ──────────────────────────────────────────────────────

variable "valid_api_keys" {
  description = "List of valid X-API-Key values for the SecurityMiddleware."
  type        = list(string)
  sensitive   = true
}

# ── Container App sizing ──────────────────────────────────────────────────────

variable "container_cpu" {
  description = "vCPU allocated per container replica."
  type        = number
  default     = 0.5
}

variable "container_memory" {
  description = "Memory allocated per container replica (e.g. '1Gi')."
  type        = string
  default     = "1Gi"
}

variable "min_replicas" {
  description = "Minimum number of Container App replicas (0 = scale to zero)."
  type        = number
  default     = 1
}

variable "max_replicas" {
  description = "Maximum number of Container App replicas."
  type        = number
  default     = 5
}

variable "image_tag" {
  description = "Docker image tag to deploy (e.g. git commit SHA or 'latest')."
  type        = string
  default     = "latest"
}

