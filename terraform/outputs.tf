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
