# ============================================
# TERRAFORM OUTPUTS
# ============================================

# ----------------
# Resource Group
# ----------------
output "resource_group_name" {
  description = "Resource Group name"
  value       = azurerm_resource_group.main.name
}

output "resource_group_location" {
  description = "Resource Group location"
  value       = azurerm_resource_group.main.location
}

# ----------------
# Networking
# ----------------
output "vnet_id" {
  description = "Virtual Network ID"
  value       = azurerm_virtual_network.main.id
}

output "vnet_name" {
  description = "Virtual Network name"
  value       = azurerm_virtual_network.main.name
}

output "vnet_address_space" {
  description = "Virtual Network address space"
  value       = azurerm_virtual_network.main.address_space
}

output "gateway_subnet_id" {
  description = "Gateway Subnet ID"
  value       = azurerm_subnet.gateway.id
}

output "app_subnet_id" {
  description = "App Service Subnet ID"
  value       = azurerm_subnet.app.id
}

output "container_subnet_id" {
  description = "Container Instances Subnet ID"
  value       = azurerm_subnet.container.id
}

output "nsg_id" {
  description = "Network Security Group ID"
  value       = azurerm_network_security_group.main.id
}

# ----------------
# Summary
# ----------------
output "deployment_summary" {
  sensitive   = true
  description = "Deployment summary"
  value = {
    subscription_id = var.azure_subscription_id
    region          = var.location
    resource_group  = azurerm_resource_group.main.name
    vnet            = azurerm_virtual_network.main.name
    environment     = var.environment
  }
}
<<<<<<< HEAD
# ================================
# PHASE 8: Frontend Dashboard
# ================================

# SignalR Service Connection String
output "signalr_connection_string" {
  description = "Azure SignalR Service connection string for WebSocket real-time communication"
  value       = azurerm_signalr_service.main.primary_connection_string
  sensitive   = true
}

output "signalr_hostname" {
  description = "SignalR Service hostname (public endpoint)"
  value       = azurerm_signalr_service.main.hostname
}

# Static Web App Deployment Token
output "static_web_app_api_token" {
  description = "API token for deploying to Azure Static Web App via GitHub Actions"
  value       = azurerm_static_site.main.api_key
  sensitive   = true
}

output "static_web_app_url" {
  description = "Static Web App default hostname (public URL)"
  value       = azurerm_static_site.main.default_host_name
}

# b616671 (✅ Phase 1 Complete: Azure Infrastructure via Terraform)
