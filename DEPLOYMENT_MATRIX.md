# Crossplane Multi-CDN Deployment Matrix

**Generated Date:** April 6, 2026  
**Demo:** EKS Crossplane Multi-CDN Demo  
**Status:** ✅ Active (SYNCED: True, READY: True)

---

## 1. ARCHITECTURE OVERVIEW

```
User Request
    ↓
XDeliveryService (Composite Resource)
    ↓
Crossplane Composition Pipeline (xdeliveryservice-demo)
    ├─→ Patch & Transform Function
    │    ├─→ Provider Config: in-cluster (Kubernetes)
    │    └─→ Renders manifests from input parameters
    ↓
Child Resources (ConfigMaps) → Adapters
    ├─→ summary (observational)
    ├─→ certificate-request → Certificate Authority Adapter
    ├─→ dns-request → DNS Adapter (internal-api mode)
    ├─→ identity-request → Identity Provider Adapter (IDAnywhere)
    ├─→ cloudflare-native-request → Cloudflare Native API Adapter
    └─→ akamai-terraform-request → Akamai Terraform Module Adapter
```

---

## 2. COMPONENT MATRIX

| **Component** | **Type** | **Kind** | **Namespace** | **Purpose** | **Status** |
|---|---|---|---|---|---|
| **Infrastructure** | | | | | |
| provider-kubernetes | Provider Package | Provider | crossplane-system | Enable Kubernetes Object management in Crossplane | ✅ Ready |
| function-patch-and-transform | Crossplane Function | ClusterExtensionPackage | crossplane-system | Patch & Transform pipeline function for composition logic | ✅ Ready |
| in-cluster | Provider Config | ProviderConfig | crossplane-system | In-cluster Kubernetes API access for resource management | ✅ Ready |
| **API & Schema Definitions** | | | | | |
| xdeliveryservices.delivery.bank.demo | CRD | CompositeResourceDefinition | crossplane-system | Defines XDeliveryService API (v1alpha1) | ✅ Ready |
| xdeliveryservice-demo | Composition | Composition | crossplane-system | Orchestrates multi-CDN resource provisioning pipeline | ✅ Ready |
| **User-Facing Resources** | | | | | |
| static-assets | Composite | XDeliveryService | crossplane-system | Demo delivery service claim for multi-CDN setup | ✅ SYNCED & READY |
| **Managed Child Resources** | | | | | |
| static-assets-summary | ConfigMap | Object | crossplane-system | Service metadata summary for operational visibility | ✅ Ready |
| static-assets-certificate-request | ConfigMap | Object | crossplane-system | Certificate provisioning request (ACME/custom CA) | ✅ Ready |
| static-assets-dns-request | ConfigMap | Object | crossplane-system | DNS configuration request (internal-api routing) | ✅ Ready |
| static-assets-identity-request | ConfigMap | Object | crossplane-system | Identity provider request (IDAnywhere integration) | ✅ Ready |
| static-assets-cloudflare-native-request | ConfigMap | Object | crossplane-system | Cloudflare native API adapter configuration | ✅ Ready |
| static-assets-akamai-terraform-request | ConfigMap | Object | crossplane-system | Akamai Terraform module adapter configuration | ✅ Ready |
| **Web Frontend** | | | | | |
| demo-html-configmap | ConfigMap | ConfigMap | default | Demo HTML UI (static content) | ✅ Ready |
| nginx-deployment | Deployment | Deployment | default | Nginx reverse proxy for demo dashboard | ✅ Ready |
| nginx-service | Service | Service | default | Nginx LoadBalancer service (exposes demo dashboard) | ✅ Ready |

---

## 3. RESOURCE DEPLOYMENT TREE

```
CLUSTER ROOT
├── crossplane-system (Namespace)
│   ├── INFRASTRUCTURE COMPONENTS
│   │   ├── Crossplane Operators (system pods)
│   │   ├── Provider: provider-kubernetes
│   │   ├── Function: function-patch-and-transform
│   │   └── ProviderConfig: in-cluster
│   │
│   ├── API SCHEMA LAYER
│   │   ├── CompositeResourceDefinition
│   │   │   └── xdeliveryservices.delivery.bank.demo
│   │   │       └── Schema: XDeliveryService (v1alpha1)
│   │   │           ├── Required: serviceName, team, lob, hostname
│   │   │           ├── Optional: pathPrefix, cacheTtlSeconds
│   │   │           └── Advanced: executionMode, dnsMode, certificateMode
│   │   │
│   │   └── Composition: xdeliveryservice-demo
│   │       └── Pipeline Step: render-artifacts
│   │           └── Function: function-patch-and-transform
│   │
│   └── RUNTIME RESOURCES
│       ├── XDeliveryService Claim
│       │   └── static-assets (SYNCED: True, READY: True)
│       │
│       └── Managed Child Resources (Composite)
│           ├── Object: static-assets-6b3df0c9b994 (summary)
│           ├── Object: static-assets-<hash> (certificate-request)
│           ├── Object: static-assets-<hash> (dns-request)
│           ├── Object: static-assets-<hash> (identity-request)
│           ├── Object: static-assets-<hash> (cloudflare-native-request)
│           └── Object: static-assets-<hash> (akamai-terraform-request)
│
└── default (Namespace)
    └── WEB FRONTEND
        ├── ConfigMap: demo-html-configmap
        ├── Deployment: nginx-deployment
        └── Service: nginx-service (LoadBalancer)
```

---

## 4. DATA FLOW: REQUEST → ADAPTATION

```
INPUT PARAMETERS (static-assets claim)
│
├─ serviceName: "static-assets"
├─ hostname: "assets.bank.example"
├─ team: "digital-content-platform"
├─ lob: "ccb-digital"
├─ originHost: "assets-use1.s3-website-us-east-1.amazonaws.com"
├─ secondaryOriginHost: "assets-usw2.s3-website-us-west-2.amazonaws.com"
├─ cacheTtlSeconds: 3600
├─ dnsMode: "internal-api"
├─ certificateMode: "acme-or-custom-ca"
├─ identityProvider: "IDAnywhere"
├─ executionMode.akamai: "terraform"
└─ executionMode.cloudflare: "native-api"
         ↓
    COMPOSITION ENGINE
    (xdeliveryservice-demo)
         ↓
    PATCH & TRANSFORM
    (function-patch-and-transform)
         ↓
    COMBINED TEMPLATES
         ↓
    MANAGED CHILD RESOURCES
    ├─ Summary ConfigMap (consolidated metadata)
    ├─ Certificate Request → Certificate Authority
    ├─ DNS Request → Internal DNS API
    ├─ Identity Request → IDAnywhere Provider
    ├─ Cloudflare Request → Cloudflare Native API
    └─ Akamai Request → Terraform Module Executor
         ↓
    EXTERNAL ADAPTERS APPLY CONFIGURATION
    ├─ Akamai: Terraform applies ./terraform/akamai_static_assets_module
    │  └─ Creates: CDN service, routing rules, cache policies
    ├─ Cloudflare: Native API creates zones, DNS records, cache settings
    │  └─ Creates: DNS, routing, SSL/TLS, WAF rules
    ├─ Certificate: Provisions TLS certificate
    ├─ DNS: Routes internal.assets.bank.example to internal ALB
    └─ Identity: Configures IDAnywhere authentication
         ↓
    DELIVERY SERVICE READY
    (SYNCED: True, READY: True)
```

---

## 5. COMPONENT DEPENDENCIES & RELATIONSHIPS

### Direct Dependencies:
```
static-assets (XDeliveryService)
    ↓ owns via controller
xdeliveryservice-demo (Composition)
    ↓ requires
xdeliveryservice-demo-<revision> (CompositionRevision)
    ↓ invokes
function-patch-and-transform
    ↓ executes on
provider-kubernetes
    ↓ uses credentials from
in-cluster (ProviderConfig)
    ↓ applies to
Kubernetes API (in-cluster)
```

### Resource Generation Chain:
```
XDeliveryService spec
    ↓ (via composition patches)
CombineFromComposite transformations
    ↓ (generates JSON payloads)
ConfigMap Data Fields
    ├─ provider: (akamai|cloudflare)
    ├─ adapterType: (terraform-module|native-api)
    ├─ variables|tfvars: (JSON configuration)
    └─ ... (adapter-specific fields)
    ↓ (read by external adapters)
External System Configuration
```

---

## 6. MANIFEST FILES INVENTORY

### Base Infrastructure (`/manifests/base/`)
| File | Component | Purpose |
|---|---|---|
| `provider-kubernetes.yaml` | Provider | Install Kubernetes provider for Crossplane |
| `function-patch-and-transform.yaml` | Function | Install patch-and-transform pipeline function |
| `provider-kubernetes-providerconfig.yaml` | ProviderConfig | Configure in-cluster Kubernetes access |
| `optional-provider-aws-secret.example.yaml` | Secret | (Optional) AWS credentials for AWS provider |
| `optional-provider-aws-providerconfig.example.yaml` | ProviderConfig | (Optional) AWS provider configuration |

### Demo Configuration (`/manifests/demo/`)
| File | Component | Purpose |
|---|---|---|
| `namespace.yaml` | Namespace | Create crossplane-system namespace |
| `xdeliveryservice-xrd.yaml` | XRD | Define XDeliveryService composite resource API |
| `xdeliveryservice-composition.yaml` | Composition | Orchestrate multi-CDN resource provisioning |
| `static-assets-claim.yaml` | Claim | Example delivery service request |

### Web Frontend (`/manifests/web/`)
| File | Component | Purpose |
|---|---|---|
| `demo-html-configmap.yaml` | ConfigMap | Dashboard HTML/assets content |
| `nginx-deployment.yaml` | Deployment | Deploy Nginx reverse proxy |
| `nginx-service.yaml` | Service | Expose Nginx via LoadBalancer |

---

## 7. API ENDPOINTS & INTERFACES

### Kubernetes APIs
```
Core Resources:
- ConfigMap (v1): Store adapter configuration
- Namespace (v1): Organize resources
- Deployment (v1): Run web frontend
- Service (v1): Expose services

Crossplane Custom Resources:
- CompositeResourceDefinition (apiextensions.crossplane.io/v1)
  Group: delivery.bank.demo, Version: v1alpha1
  Kind: XDeliveryService (Plural: xdeliveryservices)

- Composition (apiextensions.crossplane.io/v1)
  Name: xdeliveryservice-demo
  Type: Pipeline with patch-and-transform

- Provider (pkg.crossplane.io/v1)
  Name: provider-kubernetes
  Version: v1.0.0

- Function (pkg.crossplane.io/v1beta1)
  Name: function-patch-and-transform
```

### Custom Claims API
```yaml
apiVersion: delivery.bank.demo/v1alpha1
kind: XDeliveryService
metadata:
  name: <service-name>
spec:
  serviceName: string (required)
  team: string (required)
  lob: string (required)
  hostname: string (required)
  runtimeAlbHost: string (required)
  originHost: string (required)
  secondaryOriginHost: string (required)
  pathPrefix: string (default: /static)
  cacheTtlSeconds: integer (default: 3600)
  htmlCachePolicy: string (default: inherit)
  identityProvider: string (default: IDAnywhere)
  dnsMode: string (default: internal-api)
  certificateMode: string (default: acme-or-custom-ca)
  executionMode:
    akamai: string (default: terraform)
    cloudflare: string (default: native-api)
```

---

## 8. DEPLOYMENT SCRIPTS USAGE

| Script | Purpose | Order |
|---|---|---|
| `00-create-eks-cluster.sh` | Provision EKS cluster in AWS | 1st |
| `01-bootstrap-crossplane.sh` | Install Crossplane and base components | 2nd |
| `02-install-demo.sh` | Deploy demo composition, XRD, and claim | 3rd |
| `03-deploy-web.sh` | Deploy Nginx dashboard frontend | 4th |
| `04-get-demo-url.sh` | Retrieve LoadBalancer endpoint URL | 5th |
| `05-inspect-demo.sh` | Show status of XDeliveryService and resources | 6th |

---

## 9. CURRENT DEPLOYMENT STATUS

```
CLUSTER STATUS:
✅ EKS Cluster: Running
✅ Crossplane System: Deployed & Operational

CROSSPLANE RESOURCES:
✅ Provider (provider-kubernetes): Ready
✅ Function (function-patch-and-transform): Ready
✅ ProviderConfig (in-cluster): Configured

API & SCHEMA:
✅ CompositeResourceDefinition (xdeliveryservices): Active
✅ Composition (xdeliveryservice-demo): Ready

DEMO RESOURCES:
✅ XDeliveryService (static-assets): SYNCED=True, READY=True
  ├── Summary: ✅ Ready
  ├── Certificate Request: ✅ Ready
  ├── DNS Request: ✅ Ready
  ├── Identity Request: ✅ Ready
  ├── Cloudflare Adapter: ✅ Ready
  └── Akamai Terraform Adapter: ✅ Ready

WEB FRONTEND:
✅ Nginx Deployment: Running
✅ Nginx Service: LoadBalancer Active
✅ Demo Dashboard: Accessible
```

---

## 10. KEY DESIGN PATTERNS

### 1. **Infrastructure as Code (IaC)**
- All resources defined in YAML manifests
- Composable, versioned, and repeatable
- Pipeline-based orchestration (Crossplane Pipeline Mode)

### 2. **Multi-Cloud Abstraction**
- Single XDeliveryService API hides multi-CDN complexity
- Supports multiple adapters (Akamai, Cloudflare, etc.)
- Extensible adapter pattern for new providers

### 3. **Declarative Resource Management**
- Status shows intent vs. actual state
- Automatic reconciliation loops
- Health monitoring built-in

### 4. **Composition-Based Ordering**
- Patch & Transform executes transformations
- CombineFromComposite merges values into JSON
- Conditional logic supported via transforms

### 5. **Adapter Pattern**
- ConfigMaps carry adapter specifications
- External systems read and apply configuration
- Decouples Crossplane from provider implementations

---

## 11. TROUBLESHOOTING REFERENCE

| Error | Root Cause | Resolution |
|---|---|---|
| ConfigMap data unmarshal error | Nested objects in ConfigMap data (e.g., tfvars.json) | Use flat keys only (tfvars instead of tfvars.json) |
| SYNCED=False | Resource creation failed | Check composition, provider credentials, manifests |
| READY=False | Child resources not ready | Verify all ConfigMaps created, check adapter status |
| Provider not available | Provider package not installed | Run `01-bootstrap-crossplane.sh` |
| Function not found | Pipeline function not deployed | Verify function-patch-and-transform in manifests |

---

## 12. QUICK REFERENCE COMMANDS

```bash
# Check overall status
./05-inspect-demo.sh

# See full XDeliveryService details
kubectl describe xdeliveryservice.delivery.bank.demo static-assets -n crossplane-system

# Inspect specific adapter ConfigMap
kubectl get configmap static-assets-akamai-terraform-request -n crossplane-system -o yaml

# Monitor reconciliation
kubectl logs -n crossplane-system -l app.kubernetes.io/name=crossplane -f

# Get demo URL
./04-get-demo-url.sh

# Delete and redeploy
kubectl delete xdeliveryservice.delivery.bank.demo static-assets -n crossplane-system
./02-install-demo.sh
```

---

**End of Deployment Matrix**
