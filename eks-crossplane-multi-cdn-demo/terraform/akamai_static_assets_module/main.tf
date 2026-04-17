terraform {
  required_version = ">= 1.3.0"
  required_providers {
    akamai = {
      source  = "akamai/akamai"
      version = "~> 5.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.11"
    }
  }
}

variable "service_name" {
  description = "Name of the delivery service"
  type        = string
}

variable "hostname" {
  description = "Public hostname to attach to Akamai property"
  type        = string
}

variable "primary_origin" {
  description = "Primary origin host or URL"
  type        = string
}

variable "secondary_origin" {
  description = "Secondary origin host or URL"
  type        = string
  default     = ""
}

variable "path_prefix" {
  description = "Path prefix for static assets"
  type        = string
  default     = "/static"
}

variable "allowed_paths" {
  description = "Allowlisted request paths (all others are blocked)"
  type        = list(string)
  default     = ["/healthz", "/static/mdemo.html"]
}

variable "cache_ttl_seconds" {
  description = "Cache TTL in seconds"
  type        = number
  default     = 3600
}

variable "html_cache_policy" {
  description = "HTML caching policy (inherit or no-store)"
  type        = string
  default     = "inherit"
  validation {
    condition     = contains(["inherit", "no-store"], lower(var.html_cache_policy))
    error_message = "html_cache_policy must be inherit or no-store"
  }
}

variable "owner_team" {
  description = "Owning team label"
  type        = string
}

variable "owner_lob" {
  description = "LOB/group name used for Akamai lookups"
  type        = string
}

variable "runtime_alb_host" {
  description = "Runtime ALB host (not used directly in this baseline module)"
  type        = string
  default     = ""
}

variable "dns_mode" {
  description = "DNS mode metadata"
  type        = string
  default     = "internal-api"
}

variable "certificate_mode" {
  description = "Certificate mode metadata"
  type        = string
  default     = "acme-or-custom-ca"
}

variable "identity_provider" {
  description = "Identity provider metadata"
  type        = string
  default     = "IDAnywhere"
}

variable "network" {
  description = "Akamai activation network"
  type        = string
  default     = "STAGING"
  validation {
    condition     = contains(["STAGING", "PRODUCTION"], var.network)
    error_message = "network must be STAGING or PRODUCTION"
  }
}

variable "activate_property" {
  description = "Whether to activate the property after creation"
  type        = bool
  default     = false
}

variable "product_id" {
  description = "Akamai product ID for Property Manager"
  type        = string
  default     = "prd_Fresca"
}

variable "rule_format" {
  description = "Property Manager rule format version"
  type        = string
  default     = "v2023-01-05"
}

variable "contract_id" {
  description = "Optional explicit Akamai contract ID (ctr_...)"
  type        = string
  default     = ""
}

variable "group_id" {
  description = "Optional explicit Akamai group ID (grp_...)"
  type        = string
  default     = ""
}

variable "run_timestamp" {
  description = "UTC timestamp injected by adapter for audit comments"
  type        = string
  default     = ""
}

locals {
  safe_service_name = replace(lower(var.service_name), "_", "-")
  safe_hostname     = replace(replace(lower(var.hostname), ".", "-"), "*", "wildcard")
  safe_product_id   = replace(lower(var.product_id), "prd_", "")
  property_name     = "${local.safe_hostname}_pm"
  cp_code_name      = "${local.safe_service_name}-cp-code"
  edge_hostname     = "${lower(var.hostname)}.edgesuite.net"
  primary_origin_host = replace(replace(var.primary_origin, "https://", ""), "http://", "")
  secondary_origin_host = replace(replace(var.secondary_origin, "https://", ""), "http://", "")
  cp_code_numeric_id = tonumber(replace(akamai_cp_code.cp_code.id, "cpc_", ""))
  has_secondary_origin = var.secondary_origin != "" && var.secondary_origin != "https://"
  html_no_store = lower(var.html_cache_policy) == "no-store"

  # Demo guardrail: keep Akamai in cache-only provisioning mode.
  # Property activation is intentionally disabled to avoid cert/quota dependencies.
  enable_property_activation = false

  # Build the Akamai rule tree with:
  #   - cpCode, origin, healthDetection, caching
  # ALB Cloudlets are intentionally disabled for demo stability.
  akamai_rule_tree = jsonencode({
    comments = "Managed by Terraform demo module using crossplane"
    rules = {
      name     = "default"
      criteria = []
      children = concat([
        {
          name = "Block non-allowlisted paths"
            criteriaMustSatisfy = "all"
            criteria             = [
            {
              name = "path"
              options = {
                matchOperator      = "DOES_NOT_MATCH_ONE_OF"
                values             = var.allowed_paths
                matchCaseSensitive = false
              }
            }
          ]
          behaviors = [
            {
              name = "denyAccess"
              options = {
                enabled = true
              }
            }
          ]
          children = []
        }
      ], local.html_no_store ? [
        {
          name = "Disable HTML cache"
            criteriaMustSatisfy = "all"
            criteria             = [
            {
              name = "path"
              options = {
                matchOperator      = "MATCHES_ONE_OF"
                values             = ["${var.path_prefix}/*.html"]
                matchCaseSensitive = false
              }
            }
          ]
          behaviors = [
            {
              name = "caching"
              options = {
                behavior       = "NO_STORE"
                mustRevalidate = false
              }
            }
          ]
          children = []
        }
      ] : [], [
        {
          name = "Static asset caching"
            criteriaMustSatisfy = "all"
            criteria             = [
            {
              name = "path"
              options = {
                matchOperator      = "MATCHES_ONE_OF"
                values             = ["${var.path_prefix}/*"]
                matchCaseSensitive = false
              }
            },
            {
              name = "path"
              options = {
                matchOperator      = "DOES_NOT_MATCH_ONE_OF"
                values             = ["${var.path_prefix}/*.html"]
                matchCaseSensitive = false
              }
            }
          ]
          behaviors = [
            {
              name = "caching"
              options = {
                behavior       = "MAX_AGE"
                mustRevalidate = false
                ttl            = "${var.cache_ttl_seconds}s"
              }
            },
            {
              name = "downstreamCache"
              options = {
                behavior      = "ALLOW"
                allowBehavior = "LESSER"
                ttl           = "${floor(var.cache_ttl_seconds / 2)}s"
                sendHeaders   = "CACHE_CONTROL"
              }
            }
          ]
          children = []
        }
      ])
      behaviors = [
        {
          name = "globalRequestNumber"
          options = {
            outputOption = "RESPONSE_HEADER"
            headername   = "x-ak-trace-id"
          }
        },
        {
          name = "cpCode"
          options = {
            value = {
              id   = local.cp_code_numeric_id
              name = local.cp_code_name
            }
          }
        },
        {
          name = "origin"
          options = {
            originType         = "CUSTOMER"
            hostname           = local.primary_origin_host
            forwardHostHeader  = "ORIGIN_HOSTNAME"
            cacheKeyHostname   = "ORIGIN_HOSTNAME"
            httpPort           = 80
            httpsPort          = 80
            verificationMode   = "PLATFORM_SETTINGS"
            compress           = true
            enableTrueClientIp = true
          }
        },
        {
          name = "healthDetection"
          options = {
            retryCount        = 3
            retryInterval     = "10s"
            maximumReconnects = 3
          }
        }
      ]
    }
  })
}

data "akamai_contract" "contract" {
  count      = var.contract_id == "" ? 1 : 0
  group_name = var.owner_lob
}

data "akamai_group" "group" {
  count       = var.group_id == "" ? 1 : 0
  contract_id = local.resolved_contract_id
  group_name  = var.owner_lob
}

locals {
  resolved_contract_id = var.contract_id != "" ? var.contract_id : data.akamai_contract.contract[0].id
  resolved_group_id    = var.group_id != "" ? var.group_id : data.akamai_group.group[0].id
}

resource "akamai_cp_code" "cp_code" {
  name        = local.cp_code_name
  contract_id = local.resolved_contract_id
  group_id    = local.resolved_group_id
  product_id  = var.product_id
}

resource "akamai_edge_hostname" "edge_hostname" {
  contract_id   = local.resolved_contract_id
  group_id      = local.resolved_group_id
  product_id    = var.product_id
  edge_hostname = local.edge_hostname
  ip_behavior   = "IPV4"
}

resource "akamai_property" "cdn" {
  name        = local.property_name
  contract_id = local.resolved_contract_id
  group_id    = local.resolved_group_id
  product_id  = var.product_id
  rule_format = var.rule_format
  rules       = local.akamai_rule_tree

  hostnames {
    cname_from             = var.hostname
    cname_to               = akamai_edge_hostname.edge_hostname.edge_hostname
    cert_provisioning_type = "CPS_MANAGED"
  }
}

resource "akamai_property_activation" "activation" {
  count       = local.enable_property_activation ? 1 : 0
  property_id = akamai_property.cdn.id
  version     = akamai_property.cdn.latest_version
  network     = var.network
  contact     = ["${var.owner_team}@bank.example"]
}

output "property_id" {
  value = akamai_property.cdn.id
}

output "property_name" {
  value = akamai_property.cdn.name
}

output "hostname" {
  value = var.hostname
}

output "edge_hostname" {
  value = akamai_edge_hostname.edge_hostname.edge_hostname
}

output "cp_code" {
  value = akamai_cp_code.cp_code.id
}

output "contract_id" {
  value = local.resolved_contract_id
}

output "group_id" {
  value = local.resolved_group_id
}

output "version" {
  value = akamai_property.cdn.latest_version
}

output "activation_status" {
  value = local.enable_property_activation ? akamai_property_activation.activation[0].status : "SKIPPED"
}

output "delivery_plan_json" {
  value = jsonencode({
    service_name      = var.service_name
    hostname          = var.hostname
    primary_origin    = local.primary_origin_host
    secondary_origin  = var.secondary_origin
    path_prefix       = var.path_prefix
    cache_ttl_seconds = var.cache_ttl_seconds
    owner_team        = var.owner_team
    owner_lob         = var.owner_lob
    dns_mode          = var.dns_mode
    certificate_mode  = var.certificate_mode
    identity_provider = var.identity_provider
    network           = var.network
    akamai = {
      property_id      = akamai_property.cdn.id
      property_name    = akamai_property.cdn.name
      property_version = akamai_property.cdn.latest_version
      cp_code          = akamai_cp_code.cp_code.id
      edge_hostname    = akamai_edge_hostname.edge_hostname.edge_hostname
      contract_id      = local.resolved_contract_id
      group_id         = local.resolved_group_id
      activation       = local.enable_property_activation ? akamai_property_activation.activation[0].status : "SKIPPED"
    }
  })
}
