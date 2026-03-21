##############################################################################
# outputs.tf — values printed after `terraform apply`
##############################################################################

output "resource_group_name" {
  description = "Resource group that contains all resources."
  value       = azurerm_resource_group.main.name
}

output "container_app_fqdn" {
  description = <<EOT
Internal FQDN of the Container App (only reachable from within the VNet).
To expose it publicly, place an Application Gateway or Azure Front Door in front.
EOT
  value       = azurerm_container_app.api.latest_revision_fqdn
}

output "container_app_name" {
  description = "Container App resource name — use this in CI/CD update commands."
  value       = azurerm_container_app.api.name
}

output "acr_login_server" {
  description = "ACR login server — used in docker push and az acr build commands."
  value       = azurerm_container_registry.main.login_server
}

output "openai_endpoint" {
  description = "Azure OpenAI private endpoint URL — set as OPENAI_API_BASE in the app."
  value       = azurerm_cognitive_account.openai.endpoint
}

output "mysql_fqdn" {
  description = "MySQL Flexible Server FQDN (private, VNet-internal only)."
  value       = azurerm_mysql_flexible_server.main.fqdn
}

output "key_vault_uri" {
  description = "Key Vault URI — used to reference secrets in Container App config."
  value       = azurerm_key_vault.main.vault_uri
}

output "managed_identity_client_id" {
  description = "Client ID of the User-Assigned Managed Identity — for Azure SDK auth."
  value       = azurerm_user_assigned_identity.api.client_id
}

output "vnet_id" {
  description = "VNet resource ID — useful for peering with on-premises or hub networks."
  value       = azurerm_virtual_network.main.id
}

output "deploy_command" {
  description = "Quick reference: how to push a new image and trigger a revision update."
  value       = <<EOT
# 1. Build and push the image
az acr build \
  --registry ${azurerm_container_registry.main.name} \
  --image ${var.project}:$(git rev-parse --short HEAD) \
  --file Dockerfile .

# 2. Update the Container App to the new image tag
az containerapp update \
  --name ${azurerm_container_app.api.name} \
  --resource-group ${azurerm_resource_group.main.name} \
  --image ${azurerm_container_registry.main.login_server}/${var.project}:$(git rev-parse --short HEAD)
EOT
}

