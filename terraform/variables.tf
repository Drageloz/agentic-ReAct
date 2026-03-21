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
  default     = 30 # 30k TPM — adjust to your quota
}

# ── MySQL ─────────────────────────────────────────────────────────────────────

variable "mysql_admin_user" {
  description = "Administrator login for MySQL Flexible Server."
  type        = string
  default     = "reactadmin"
}

variable "mysql_password" {
  description = "Administrator password for MySQL Flexible Server — stored in Key Vault."
  type        = string
  sensitive   = true
}

variable "mysql_database" {
  description = "Name of the application database."
  type        = string
  default     = "react_db"
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

