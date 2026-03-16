# ============================================
# MAIN TERRAFORM CONFIGURATION
# ============================================
# SPY Options Platform - Azure Infrastructure
# Phase 1: Complete 14-resource deployment

# ----------------
# RESOURCE GROUP
# ----------------
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.common_tags
}

# ----------------
# VIRTUAL NETWORK
# ----------------
resource "azurerm_virtual_network" "main" {
  name                = var.vnet_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = var.vnet_address_space
  tags                = var.common_tags
}

# ----------------
# SUBNETS
# ----------------

# Gateway Subnet (for VPN Gateway)
resource "azurerm_subnet" "gateway" {
  name                 = "GatewaySubnet" # Must be named exactly "GatewaySubnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.gateway_subnet_prefix]
}

# App Service Subnet
resource "azurerm_subnet" "app" {
  name                 = "AppSubnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.app_subnet_prefix]

  delegation {
    name = "app-service-delegation"
    service_delegation {
      name    = "Microsoft.Web/serverFarms"
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
    }
  }
}

# Container Subnet
resource "azurerm_subnet" "container" {
  name                 = "ContainerSubnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.container_subnet_prefix]

  delegation {
    name = "container-delegation"
    service_delegation {
      name    = "Microsoft.ContainerInstance/containerGroups"
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
    }
  }
}

# ----------------
# NETWORK SECURITY GROUP
# ----------------
resource "azurerm_network_security_group" "main" {
  name                = "nsg-${var.project_name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.common_tags

  # VPN IKE (UDP 500)
  security_rule {
    name                       = "Allow-VPN-IKE"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Udp"
    source_port_range          = "*"
    destination_port_range     = "500"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # VPN NAT-T (UDP 4500)
  security_rule {
    name                       = "Allow-VPN-NAT-T"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Udp"
    source_port_range          = "*"
    destination_port_range     = "4500"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # HTTPS (TCP 443)
  security_rule {
    name                       = "Allow-HTTPS"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # Deny all other inbound
  security_rule {
    name                       = "Deny-All-Inbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

# Associate NSG with App Subnet
resource "azurerm_subnet_network_security_group_association" "app" {
  subnet_id                 = azurerm_subnet.app.id
  network_security_group_id = azurerm_network_security_group.main.id
}

# ----------------
# VPN GATEWAY
# ----------------

# Public IP for VPN Gateway
resource "azurerm_public_ip" "vpn_gateway" {
  name                = "pip-vpn-gateway"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
  zones               = ["1", "2", "3"]
  tags                = var.common_tags
}

# VPN Gateway (Site-to-Site)
resource "azurerm_virtual_network_gateway" "vpn" {
  name                = "vpn-gateway-${var.project_name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  type                = "Vpn"
  vpn_type            = "RouteBased"
  sku                 = "Basic" # $27/mo
  tags                = var.common_tags

  ip_configuration {
    name                          = "vnetGatewayConfig"
    public_ip_address_id          = azurerm_public_ip.vpn_gateway.id
    private_ip_address_allocation = "Dynamic"
    subnet_id                     = azurerm_subnet.gateway.id
  }

  # Note: This resource takes 30-45 minutes to provision
}

# Local Network Gateway (represents on-premises network)
resource "azurerm_local_network_gateway" "onprem" {
  count               = var.onprem_public_ip != "" ? 1 : 0
  name                = "lng-onprem"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  gateway_address     = var.onprem_public_ip
  address_space       = var.onprem_address_space
  tags                = var.common_tags
}

# VPN Connection (Site-to-Site)
resource "azurerm_virtual_network_gateway_connection" "onprem" {
  count                      = var.onprem_public_ip != "" && var.vpn_shared_key != "" ? 1 : 0
  name                       = "vpn-connection-onprem"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  type                       = "IPsec"
  virtual_network_gateway_id = azurerm_virtual_network_gateway.vpn.id
  local_network_gateway_id   = azurerm_local_network_gateway.onprem[0].id
  shared_key                 = var.vpn_shared_key
  tags                       = var.common_tags
}

# ----------------
# AZURE CONTAINER REGISTRY
# ----------------
resource "azurerm_container_registry" "main" {
  name                = var.acr_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic" # $5/mo
  admin_enabled       = true    # For CI/CD access
  tags                = var.common_tags
}

# ----------------
# APP SERVICE
# ----------------

# App Service Plan
resource "azurerm_service_plan" "main" {
  name                = "asp-${var.project_name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  os_type             = "Linux"
  sku_name            = "B1" # $13/mo - 1 vCPU, 1.75 GB RAM
  tags                = var.common_tags
}

# Linux Web App (Backend API)
resource "azurerm_linux_web_app" "backend" {
  name                = "app-${var.project_name}-backend"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true
  tags                = var.common_tags

  site_config {
    always_on = true # Keep app loaded

    application_stack {
      python_version = "3.11"
    }

    health_check_path = "/health"
  }

  app_settings = {
    "WEBSITES_ENABLE_APP_SERVICE_STORAGE" = "false"
    "ENVIRONMENT"                         = var.environment
    "PROJECT_NAME"                        = var.project_name
    "TV_WEBHOOK_SECRET"                   = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.tv_secret.id})"
  }

  identity {
    type = "SystemAssigned" # For Key Vault access
  }
}

# ----------------
# AZURE SIGNALR SERVICE
# ----------------
resource "azurerm_signalr_service" "main" {
  name                = "signalr-${var.project_name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku {
    name     = "Free_F1" # $0/mo - 20 connections, 20K messages/day
    capacity = 1
  }
  service_mode = "Serverless" # REST API mode compatible with signalr_rest.py
  tags         = var.common_tags

  cors {
    allowed_origins = ["*"] # Configure properly in production
  }
}

# ----------------
# STORAGE ACCOUNT
# ----------------
resource "azurerm_storage_account" "main" {
  name                     = "st${replace(var.project_name, "-", "")}${var.environment}" # Must be globally unique, no hyphens
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS" # Locally Redundant Storage
  tags                     = var.common_tags
}

# Table Storage for anomaly history
resource "azurerm_storage_table" "anomalies" {
  name                 = "anomalies"
  storage_account_name = azurerm_storage_account.main.name
}

# ----------------
# LOG ANALYTICS & APPLICATION INSIGHTS
# ----------------

# Log Analytics Workspace
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${var.project_name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.common_tags
}

# Application Insights
resource "azurerm_application_insights" "main" {
  name                = "appi-${var.project_name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = var.common_tags
}

# ----------------
# KEY VAULT
# ----------------

# Get current Azure AD tenant
data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "main" {
  name                       = "kv-${var.project_name}-${random_string.kv_suffix.result}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false # Enable in production
  tags                       = var.common_tags

  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id

    secret_permissions = [
      "Get", "List", "Set", "Delete", "Recover", "Backup", "Restore", "Purge"
    ]
  }
}

# Standalone access policy for Web App Managed Identity to break circular dependency
resource "azurerm_key_vault_access_policy" "backend" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_linux_web_app.backend.identity[0].principal_id

  secret_permissions = [
    "Get", "List"
  ]
}

# Random suffix for Key Vault name (must be globally unique)
resource "random_string" "kv_suffix" {
  length  = 4
  special = false
  upper   = false
}

# 🔐 TradingView Webhook Secret in Key Vault
resource "azurerm_key_vault_secret" "tv_secret" {
  name         = "tv-webhook-secret"
  value        = var.tv_webhook_secret == "" ? random_password.tv_secret[0].result : var.tv_webhook_secret
  key_vault_id = azurerm_key_vault.main.id
}

# Generate a random secret if none provided
resource "random_password" "tv_secret" {
  count   = var.tv_webhook_secret == "" ? 1 : 0
  length  = 32
  special = true
}

# ----------------
# STATIC WEB APP
# ----------------
resource "azurerm_static_site" "main" {
  name                = "stapp-${var.project_name}"
  location            = "westeurope" # Static Web Apps have limited regions
  resource_group_name = azurerm_resource_group.main.name
  sku_tier            = "Free" # $0/mo
  sku_size            = "Free"
  tags                = var.common_tags
}

# ----------------
# DNS ZONE & RECORDS
# ----------------
resource "azurerm_dns_zone" "main" {
  name                = "0dte-spy.com"
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.common_tags
}

# Root Domain Record (@) - A Record with Alias
resource "azurerm_dns_a_record" "root" {
  name                = "@"
  zone_name           = azurerm_dns_zone.main.name
  resource_group_name = azurerm_resource_group.main.name
  ttl                 = 3600
  target_resource_id  = azurerm_static_site.main.id
}

# WWW Subdomain Record - CNAME
resource "azurerm_dns_cname_record" "www" {
  name                = "www"
  zone_name           = azurerm_dns_zone.main.name
  resource_group_name = azurerm_resource_group.main.name
  ttl                 = 3600
  record              = azurerm_static_site.main.default_host_name
}

# ----------------
# STATIC WEB APP CUSTOM DOMAINS
# ----------------

# Root Domain Link
resource "azurerm_static_site_custom_domain" "root" {
  static_site_id  = azurerm_static_site.main.id
  domain_name     = "0dte-spy.com"
  validation_type = "dns-txt-token"
}

# TXT Record for Root Domain Validation
resource "azurerm_dns_txt_record" "root_validation" {
  name                = "@"
  zone_name           = azurerm_dns_zone.main.name
  resource_group_name = azurerm_resource_group.main.name
  ttl                 = 3600

  record {
    value = azurerm_static_site_custom_domain.root.validation_token
  }
}

# WWW Domain Link
resource "azurerm_static_site_custom_domain" "www" {
  static_site_id  = azurerm_static_site.main.id
  domain_name     = "www.0dte-spy.com"
  validation_type = "cname-delegation"
}
