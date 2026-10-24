terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.90"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-terraform-state"
    storage_account_name = "sttfstategdg2026"
    container_name       = "tfstate"
    key                  = "prod.terraform.tfstate"
  }
}

provider "azurerm" {
  features {}
}

variable "location" {
  type        = string
  default     = "eastus"
  description = "Primary Azure deployment region"
}

variable "environment" {
  type        = string
  default     = "production"
  description = "Target deployment environment"
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${var.environment}-app"
  location = var.location

  tags = {
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "azurerm_app_service_plan" "asp" {
  name                = "asp-${var.environment}-app"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  kind                = "Linux"
  reserved            = true

  sku {
    tier = "Standard"
    size = "S1"
  }
}
