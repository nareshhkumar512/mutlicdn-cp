terraform {
  required_version = ">= 1.3.0"
}

variable "service_name" { type = string }
variable "hostname" { type = string }
variable "primary_origin" { type = string }
variable "secondary_origin" { type = string }
variable "path_prefix" { type = string }
variable "cache_ttl_seconds" { type = number }
variable "owner_team" { type = string }
variable "owner_lob" { type = string }

locals {
  akamai_static_assets_plan = {
    property_name     = "${var.service_name}-property"
    hostname          = var.hostname
    primary_origin    = var.primary_origin
    secondary_origin  = var.secondary_origin
    path_prefix       = var.path_prefix
    cache_ttl         = var.cache_ttl_seconds
    owner_team        = var.owner_team
    owner_lob         = var.owner_lob
  }
}

output "delivery_plan_json" {
  value = jsonencode(local.akamai_static_assets_plan)
}
