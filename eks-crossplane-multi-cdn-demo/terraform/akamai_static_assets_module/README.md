# Akamai Static Assets Module

A Terraform module for provisioning Akamai CDN configurations for static assets with multi-origin support, intelligent failover, and comprehensive caching policies.

## Overview

This module creates a complete Akamai Property Manager configuration for delivering static assets (CSS, JS, images, etc.) with:

- **Multi-origin support** with automatic failover
- **Intelligent caching** optimized for static assets
- **Security headers** and rate limiting
- **Compression** and performance optimizations
- **Monitoring** and logging integration

## Architecture

```
Internet → Akamai Edge → Origin Servers
                    ↓
            Property Manager Rules
                    ↓
        Caching + Security + Routing
```

## Prerequisites

- Akamai account with Property Manager access
- Terraform 1.3.0+
- Akamai Terraform Provider 5.0+
- Proper Akamai credentials configured

## Usage

```hcl
module "static_assets" {
  source = "./terraform/akamai_static_assets_module"

  service_name     = "my-app-assets"
  hostname         = "assets.example.com"
  primary_origin   = "https://assets-us-east-1.s3.amazonaws.com"
  secondary_origin = "https://assets-us-west-2.s3.amazonaws.com"
  path_prefix      = "/static"
  cache_ttl_seconds = 3600
  owner_team       = "platform-team"
  owner_lob        = "digital-banking"

  # Optional advanced configuration
  enable_compression = true
  enable_security_headers = true
  network = "STAGING"  # Change to PRODUCTION when ready
}
```

## Configuration Options

### Required Variables

| Variable | Type | Description | Example |
|----------|------|-------------|---------|
| `service_name` | string | Service identifier | `"my-app-assets"` |
| `hostname` | string | CDN hostname | `"assets.example.com"` |
| `primary_origin` | string | Primary origin URL | `"https://assets-us-east-1.s3.amazonaws.com"` |
| `secondary_origin` | string | Failover origin URL | `"https://assets-us-west-2.s3.amazonaws.com"` |
| `owner_team` | string | Responsible team | `"platform-team"` |
| `owner_lob` | string | Line of business | `"digital-banking"` |

### Optional Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `path_prefix` | string | `"/static"` | URL path for assets |
| `cache_ttl_seconds` | number | `3600` | Cache TTL in seconds |
| `html_cache_policy` | string | `"inherit"` | HTML caching policy (`inherit` or `no-store`) |
| `runtime_alb_host` | string | `null` | Internal ALB hostname |
| `dns_mode` | string | `"internal-api"` | DNS configuration mode |
| `certificate_mode` | string | `"acme-or-custom-ca"` | Certificate provisioning |
| `identity_provider` | string | `"IDAnywhere"` | Authentication provider |
| `enable_compression` | bool | `true` | Enable gzip compression |
| `enable_security_headers` | bool | `true` | Enable security headers |
| `network` | string | `"STAGING"` | Activation network |
| `contact_emails` | list | `[]` | Notification emails |

## Features

### Multi-Origin Support

- Primary and secondary origin configuration
- Automatic failover between origins
- Health monitoring and recovery

### Caching Optimization

- Path-based caching rules
- TTL configuration
- Cache key optimization
- Browser caching headers

### Security & Performance

- Security headers (HSTS, etc.)
- Rate limiting protection
- Gzip compression
- Origin shielding

### Monitoring & Compliance

- Activation tracking
- Compliance records
- Audit logging
- Health check endpoints

## Akamai Resources Created

1. **CP Code** - For billing and reporting
2. **Origin Property** - Origin server configuration
3. **CDN Property** - Main delivery configuration
4. **Edge Hostname** - DNS configuration
5. **Property Activation** - Deploys to Akamai network

## Property Rules Configuration

The module creates several Property Manager rules:

### Default Rule
- CP code assignment
- Basic configuration

### Static Assets Rule
- Path-based matching (`/static/*`)
- Cache TTL configuration
- Cache key settings

### Compression Rule
- Gzip compression for assets
- Content-type based

### Security Headers Rule
- HSTS headers
- Security hardening

### Rate Limiting Rule
- Abuse protection
- Request throttling

## Activation Process

1. **STAGING** - Initial deployment (default)
2. **Testing** - Validate configuration
3. **PRODUCTION** - Live deployment

```hcl
# For production deployment
module "static_assets" {
  # ... other config
  network = "PRODUCTION"
}
```

## Integration with Crossplane

This module is designed to work with the Crossplane Multi-CDN control plane:

```yaml
# Crossplane composition generates ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: static-assets-akamai-terraform-request
data:
  tfvars: |
    {
      "service_name": "static-assets",
      "hostname": "assets.bank.example",
      "primary_origin": "https://assets-use1.s3.amazonaws.com",
      "secondary_origin": "https://assets-usw2.s3.amazonaws.com",
      "cache_ttl_seconds": 3600,
      "owner_team": "digital-content-platform",
      "owner_lob": "ccb-digital"
    }
```
