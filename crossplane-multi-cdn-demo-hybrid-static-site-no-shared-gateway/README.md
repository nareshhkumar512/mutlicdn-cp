# Crossplane Hybrid Adapter Demo - Static Assets Site (No Shared Gateway)

This version models a static asset delivery site where consuming applications simply call:

- `https://assets.bank.example/...`

There is no shared gateway object in the user-facing intent.

Scenario:
- public hostname: `assets.bank.example`
- two AWS backend origins
- caching enabled for static content
- Cloudflare path shown as a native API adapter
- Akamai path shown as a Terraform module adapter

The point of the demo:
one canonical `XDeliveryService` drives different provider-specific adapter styles, while consumers only depend on the hostname.

digital-assets-platform > digital-static-content
shared-services > ccb-shared-services
