# ============================================
# TERRAFORM VARIABLES
# ============================================
# ⚠️ DO NOT set sensitive values here!
# Set via terraform.tfvars (generated from .env.project)

# ----------------
# Azure Credentials
# ----------------
variable "azure_subscription_id" {
  description = "Azure Subscription ID"
  type        = string
  sensitive   = true
  # Set in terraform.tfvars
}

variable "azure_tenant_id" {
  description = "Azure Tenant ID"
  type        = string
  sensitive   = true
  # Set in terraform.tfvars
}

# ----------------
# Project Configuration
# ----------------
variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "spy-options"
}

variable "environment" {
  description = "Environment name (dev, prod)"
  type        = string
  default     = "prod"
}

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "westeurope"
}

# ----------------
# Naming Conventions
# ----------------
variable "resource_group_name" {
  description = "Resource Group name"
  type        = string
  default     = "rg-spy-options-prod"
}

variable "vnet_name" {
  description = "Virtual Network name"
  type        = string
  default     = "vnet-spy-options"
}

variable "acr_name" {
  description = "Azure Container Registry name (must be globally unique)"
  type        = string
  default     = "acrspyoptions"
}

# ----------------
# Networking
# ----------------
variable "vnet_address_space" {
  description = "VNet address space"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "gateway_subnet_prefix" {
  description = "Gateway subnet address prefix"
  type        = string
  default     = "10.0.0.0/27"
}

variable "app_subnet_prefix" {
  description = "App Service subnet address prefix"
  type        = string
  default     = "10.0.1.0/24"
}

variable "container_subnet_prefix" {
  description = "Container instances subnet address prefix"
  type        = string
  default     = "10.0.2.0/24"
}

# ----------------
# On-Premises Configuration
# ----------------
variable "onprem_public_ip" {
  description = "On-premises public IP for VPN connection"
  type        = string
  default     = ""  # To be filled when configuring VPN
}

variable "onprem_address_space" {
  description = "On-premises network address space"
  type        = list(string)
  default     = ["192.168.1.0/24"]
}

variable "vpn_shared_key" {
  description = "Pre-shared key for VPN connection"
  type        = string
  sensitive   = true
  default     = ""  # To be set securely
}

# ----------------
# Tags
# ----------------
variable "common_tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project     = "SPY-Options-Platform"
    Environment = "Production"
    ManagedBy   = "Terraform"
    Owner       = "Nino"
    CostCenter  = "Trading-Infrastructure"
  }
}
