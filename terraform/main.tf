##############################################################################
# main.tf — agentic-ReAct on Azure
#
# Topology (all traffic stays inside the corporate VNet):
#
#   VNet (10.0.0.0/16)
#   ├── subnet-apps   (10.0.1.0/24)  → Container Apps Environment (internal)
#   ├── subnet-db     (10.0.2.0/24)  → Azure Database for MySQL Flexible
#   ├── subnet-openai (10.0.3.0/24)  → Azure OpenAI Private Endpoint
#   └── subnet-pe     (10.0.4.0/24)  → ACR + Key Vault Private Endpoints
#
#   Azure Container Apps (internal-only ingress)
#   Azure OpenAI Service  → Private Endpoint (no public access)
#   Azure Database for MySQL Flexible → VNet-integrated, no public access
#   Azure Container Registry → Private Endpoint
#   Azure Key Vault           → Private Endpoint (stores secrets)
#   Private DNS Zones         → resolve *.openai.azure.com, *.mysql.database.azure.com
#                                 etc. inside the VNet
##############################################################################

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
    azapi = {
      source  = "azure/azapi"
      version = "~> 1.13"
    }
  }

  # Uncomment to store state in Azure Blob Storage (recommended for teams)
  # backend "azurerm" {
  #   resource_group_name  = "rg-tfstate"
  #   storage_account_name = "<your-storage-account>"
  #   container_name       = "tfstate"
  #   key                  = "agentic-react.tfstate"
  # }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }
}

provider "azapi" {}

##############################################################################
# Data sources
##############################################################################

data "azurerm_client_config" "current" {}

##############################################################################
# Resource Group
##############################################################################

resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

##############################################################################
# Virtual Network & Subnets
##############################################################################

resource "azurerm_virtual_network" "main" {
  name                = "vnet-${var.project}-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  address_space       = ["10.0.0.0/16"]
  tags                = var.tags
}

# Container Apps Environment subnet — requires /23 minimum for Consumption plan
resource "azurerm_subnet" "apps" {
  name                 = "subnet-apps"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.0.0/23"]

  delegation {
    name = "delegation-containerapp"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# MySQL Flexible Server subnet
resource "azurerm_subnet" "db" {
  name                 = "subnet-db"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.2.0/24"]

  delegation {
    name = "delegation-mysql"
    service_delegation {
      name    = "Microsoft.DBforMySQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# Private Endpoints subnet (OpenAI, ACR, Key Vault)
resource "azurerm_subnet" "private_endpoints" {
  name                 = "subnet-pe"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.3.0/24"]

  # Private endpoints do NOT support subnet delegation
  private_endpoint_network_policies = "Disabled"
}

##############################################################################
# Key Vault — stores all secrets (API keys, DB password)
##############################################################################

resource "azurerm_key_vault" "main" {
  name                        = "kv-${var.project}-${var.environment}"
  resource_group_name         = azurerm_resource_group.main.name
  location                    = azurerm_resource_group.main.location
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  sku_name                    = "standard"
  soft_delete_retention_days  = 7
  purge_protection_enabled    = true

  # Disable public network access — only reachable via Private Endpoint
  public_network_access_enabled = false

  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
  }

  tags = var.tags
}

# Allow Terraform principal to write secrets during provisioning
resource "azurerm_key_vault_access_policy" "terraform" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = data.azurerm_client_config.current.object_id

  secret_permissions = ["Get", "Set", "Delete", "List", "Purge", "Recover"]
}

# Store secrets
resource "azurerm_key_vault_secret" "openai_api_key" {
  name         = "openai-api-key"
  value        = var.openai_api_key
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.terraform]
}

resource "azurerm_key_vault_secret" "mysql_password" {
  name         = "mysql-password"
  value        = var.mysql_password
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.terraform]
}

resource "azurerm_key_vault_secret" "api_keys" {
  name         = "valid-api-keys"
  value        = jsonencode(var.valid_api_keys)
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.terraform]
}

##############################################################################
# Private Endpoint — Key Vault
##############################################################################

resource "azurerm_private_endpoint" "key_vault" {
  name                = "pe-kv-${var.project}-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = azurerm_subnet.private_endpoints.id

  private_service_connection {
    name                           = "psc-kv"
    private_connection_resource_id = azurerm_key_vault.main.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "dns-group-kv"
    private_dns_zone_ids = [azurerm_private_dns_zone.key_vault.id]
  }

  tags = var.tags
}

##############################################################################
# Azure Container Registry
##############################################################################

resource "azurerm_container_registry" "main" {
  name                          = "acr${replace(var.project, "-", "")}${var.environment}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  sku                           = "Premium" # required for Private Link
  admin_enabled                 = false
  public_network_access_enabled = false     # only via Private Endpoint
  tags                          = var.tags
}

resource "azurerm_private_endpoint" "acr" {
  name                = "pe-acr-${var.project}-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = azurerm_subnet.private_endpoints.id

  private_service_connection {
    name                           = "psc-acr"
    private_connection_resource_id = azurerm_container_registry.main.id
    subresource_names              = ["registry"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "dns-group-acr"
    private_dns_zone_ids = [azurerm_private_dns_zone.acr.id]
  }

  tags = var.tags
}

##############################################################################
# Azure OpenAI Service
##############################################################################

resource "azurerm_cognitive_account" "openai" {
  name                          = "aoai-${var.project}-${var.environment}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = var.openai_location # eastus / swedencentral
  kind                          = "OpenAI"
  sku_name                      = "S0"
  public_network_access_enabled = false # CRITICAL: no public access
  tags                          = var.tags

  network_acls {
    default_action = "Deny"
  }
}

# GPT-4o deployment
resource "azurerm_cognitive_deployment" "gpt4o" {
  name                 = "gpt-4o"
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = "gpt-4o"
    version = "2024-11-20"
  }

  sku {
    name     = "GlobalStandard"
    capacity = var.openai_capacity_tpm
  }
}

# text-embedding-3-small for ChromaDB RAG
resource "azurerm_cognitive_deployment" "embeddings" {
  name                 = "text-embedding-3-small"
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = "text-embedding-3-small"
    version = "1"
  }

  sku {
    name     = "Standard"
    capacity = 120
  }
}

resource "azurerm_private_endpoint" "openai" {
  name                = "pe-aoai-${var.project}-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = azurerm_subnet.private_endpoints.id

  private_service_connection {
    name                           = "psc-aoai"
    private_connection_resource_id = azurerm_cognitive_account.openai.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "dns-group-aoai"
    private_dns_zone_ids = [azurerm_private_dns_zone.openai.id]
  }

  tags = var.tags
}

##############################################################################
# Azure Database for MySQL Flexible Server
##############################################################################

resource "azurerm_private_dns_zone" "mysql" {
  name                = "privatelink.mysql.database.azure.com"
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "mysql" {
  name                  = "vnet-link-mysql"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.mysql.name
  virtual_network_id    = azurerm_virtual_network.main.id
  registration_enabled  = false
  tags                  = var.tags
}

resource "azurerm_mysql_flexible_server" "main" {
  name                   = "mysql-${var.project}-${var.environment}"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  administrator_login    = var.mysql_admin_user
  administrator_password = var.mysql_password
  sku_name               = "GP_Standard_D2ds_v4"
  version                = "8.0.21"

  # VNet integration — no public endpoint created
  delegated_subnet_id = azurerm_subnet.db.id
  private_dns_zone_id = azurerm_private_dns_zone.mysql.id

  backup_retention_days        = 7
  geo_redundant_backup_enabled = false

  high_availability {
    mode = "Disabled" # enable SameZone/ZoneRedundant for production
  }

  tags = var.tags

  depends_on = [azurerm_private_dns_zone_virtual_network_link.mysql]
}

resource "azurerm_mysql_flexible_database" "main" {
  name                = var.mysql_database
  resource_group_name = azurerm_resource_group.main.name
  server_name         = azurerm_mysql_flexible_server.main.name
  charset             = "utf8mb4"
  collation           = "utf8mb4_unicode_ci"
}

##############################################################################
# Container Apps — Log Analytics workspace
##############################################################################

resource "azurerm_log_analytics_workspace" "main" {
  name                = "law-${var.project}-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.tags
}

##############################################################################
# Container Apps Environment (internal — no public ingress)
##############################################################################

resource "azurerm_container_app_environment" "main" {
  name                           = "cae-${var.project}-${var.environment}"
  resource_group_name            = azurerm_resource_group.main.name
  location                       = azurerm_resource_group.main.location
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.main.id

  # Deploy into the VNet subnet — all traffic stays internal
  infrastructure_subnet_id       = azurerm_subnet.apps.id
  internal_load_balancer_enabled = true # no public IP on the environment

  tags = var.tags
}

##############################################################################
# Managed Identity for the Container App
# (used to pull from ACR and read Key Vault secrets)
##############################################################################

resource "azurerm_user_assigned_identity" "api" {
  name                = "id-${var.project}-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = var.tags
}

# ACR Pull role
resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}

# Key Vault Secrets User role
resource "azurerm_role_assignment" "kv_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}

##############################################################################
# Container App — agentic-ReAct API
##############################################################################

resource "azurerm_container_app" "api" {
  name                         = "ca-${var.project}-${var.environment}"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.api.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.api.id
  }

  secret {
    name  = "openai-api-key"
    # Reference directly from Key Vault via Managed Identity
    # Format: keyvaultref:<secret-uri>,identityref:<identity-resource-id>
    value = "keyvaultref:${azurerm_key_vault.main.vault_uri}secrets/openai-api-key,identityref:${azurerm_user_assigned_identity.api.id}"
  }

  secret {
    name  = "mysql-password"
    value = "keyvaultref:${azurerm_key_vault.main.vault_uri}secrets/mysql-password,identityref:${azurerm_user_assigned_identity.api.id}"
  }

  secret {
    name  = "valid-api-keys"
    value = "keyvaultref:${azurerm_key_vault.main.vault_uri}secrets/valid-api-keys,identityref:${azurerm_user_assigned_identity.api.id}"
  }

  template {
    min_replicas = 1
    max_replicas = var.max_replicas

    container {
      name   = "api"
      image  = "${azurerm_container_registry.main.login_server}/${var.project}:${var.image_tag}"
      cpu    = var.container_cpu
      memory = var.container_memory

      # ── Application config ──────────────────────────────────────────────
      env {
        name  = "LLM_PROVIDER"
        value = "langchain"  # uses Azure OpenAI via LangChain adapter
      }
      env {
        name        = "OPENAI_API_KEY"
        secret_name = "openai-api-key"
      }
      env {
        name  = "OPENAI_MODEL"
        value = "gpt-4o"
      }
      env {
        # Point to the Azure OpenAI private endpoint, not api.openai.com
        name  = "OPENAI_API_BASE"
        value = azurerm_cognitive_account.openai.endpoint
      }
      env {
        name  = "OPENAI_API_TYPE"
        value = "azure"
      }
      env {
        name  = "OPENAI_API_VERSION"
        value = "2024-02-01"
      }
      env {
        name  = "RAG_PROVIDER"
        value = "chroma"
      }
      env {
        name  = "MYSQL_HOST"
        value = azurerm_mysql_flexible_server.main.fqdn
      }
      env {
        name  = "MYSQL_PORT"
        value = "3306"
      }
      env {
        name  = "MYSQL_USER"
        value = var.mysql_admin_user
      }
      env {
        name        = "MYSQL_PASSWORD"
        secret_name = "mysql-password"
      }
      env {
        name  = "MYSQL_DATABASE"
        value = var.mysql_database
      }
      env {
        name        = "VALID_API_KEYS"
        secret_name = "valid-api-keys"
      }
      env {
        name  = "AGENT_MAX_ITERATIONS"
        value = "10"
      }
      env {
        name  = "DEBUG"
        value = "false"
      }

      # ── Health probes ───────────────────────────────────────────────────
      liveness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 8000

        initial_delay           = 15
        period_seconds          = 20
        failure_count_threshold = 3
      }

      readiness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 8000

        initial_delay           = 10
        period_seconds          = 10
        failure_count_threshold = 3
      }
    }

    # ── Scaling rules ───────────────────────────────────────────────────
    custom_scale_rule {
      name             = "http-scaling"
      custom_rule_type = "http"
      metadata = {
        concurrentRequests = "10"
      }
    }
  }

  ingress {
    # internal = true → only reachable from within the VNet
    # Set to false and add custom_domain if you need an Application Gateway in front
    external_enabled = false
    target_port      = 8000
    transport        = "http"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  tags = var.tags

  depends_on = [
    azurerm_role_assignment.acr_pull,
    azurerm_role_assignment.kv_secrets,
    azurerm_mysql_flexible_database.main,
    azurerm_private_endpoint.openai,
  ]
}

##############################################################################
# Private DNS Zones (resolves private endpoints inside the VNet)
##############################################################################

locals {
  private_dns_zones = {
    openai  = "privatelink.openai.azure.com"
    acr     = "privatelink.azurecr.io"
    kv      = "privatelink.vaultcore.azure.net"
  }
}

resource "azurerm_private_dns_zone" "openai" {
  name                = local.private_dns_zones["openai"]
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.tags
}

resource "azurerm_private_dns_zone" "acr" {
  name                = local.private_dns_zones["acr"]
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.tags
}

resource "azurerm_private_dns_zone" "key_vault" {
  name                = local.private_dns_zones["kv"]
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.tags
}

# Link all DNS zones to the VNet
resource "azurerm_private_dns_zone_virtual_network_link" "openai" {
  name                  = "vnet-link-openai"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.openai.name
  virtual_network_id    = azurerm_virtual_network.main.id
  registration_enabled  = false
  tags                  = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "acr" {
  name                  = "vnet-link-acr"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.acr.name
  virtual_network_id    = azurerm_virtual_network.main.id
  registration_enabled  = false
  tags                  = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "key_vault" {
  name                  = "vnet-link-kv"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.key_vault.name
  virtual_network_id    = azurerm_virtual_network.main.id
  registration_enabled  = false
  tags                  = var.tags
}

