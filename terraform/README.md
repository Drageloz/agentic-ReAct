# agentic-ReAct — Azure Deployment

> Terraform que despliega la solución completa en Azure garantizando que **todo el tráfico de datos queda dentro de la red privada** de la empresa (sin salida pública).

---

## 🏛️ Arquitectura desplegada

```
                        ┌──────────── Azure VNet (10.0.0.0/16) ─────────────────┐
                        │                                                        │
  Corporative           │  subnet-apps (10.0.0.0/23)                            │
  Network / VPN  ───────┼──► Container Apps Environment (internal LB)           │
  or ExpressRoute       │        └── Container App: agentic-react-api            │
                        │               │  reads secrets via Managed Identity    │
                        │               │                                        │
                        │  subnet-pe (10.0.3.0/24)                              │
                        │       ├── Private Endpoint ──► Azure OpenAI           │
                        │       ├── Private Endpoint ──► Azure Container Registry│
                        │       └── Private Endpoint ──► Azure Key Vault        │
                        │                                                        │
                        │  subnet-db (10.0.2.0/24)                              │
                        │       └── MySQL Flexible Server (VNet-integrated)     │
                        │                                                        │
                        │  Private DNS Zones (resolve inside VNet):             │
                        │    privatelink.openai.azure.com                       │
                        │    privatelink.azurecr.io                             │
                        │    privatelink.vaultcore.azure.net                    │
                        │    privatelink.mysql.database.azure.com               │
                        └────────────────────────────────────────────────────────┘
```

### Por qué el tráfico no sale de la red privada

| Recurso | Mecanismo de aislamiento |
|---|---|
| **Azure OpenAI** | `public_network_access_enabled = false` + Private Endpoint en `subnet-pe` + Private DNS Zone `privatelink.openai.azure.com` |
| **MySQL Flexible Server** | VNet-delegation en `subnet-db` — no se crea endpoint público, solo FQDN privado |
| **Azure Container Registry** | SKU Premium + `public_network_access_enabled = false` + Private Endpoint |
| **Azure Key Vault** | `public_network_access_enabled = false` + Private Endpoint + `network_acls default_action = Deny` |
| **Container Apps Environment** | `internal_load_balancer_enabled = true` — sin IP pública, ingress solo interno |
| **Container App** | `external_enabled = false` — solo accesible desde dentro del VNet o via Application Gateway |

---

## 📁 Estructura de archivos

```
terraform/
├── main.tf                   # Todos los recursos Azure
├── variables.tf              # Declaración y validación de variables
├── outputs.tf                # Valores útiles tras apply (FQDN, ACR, etc.)
├── terraform.tfvars.example  # Plantilla de valores — copiar a terraform.tfvars
└── README.md                 # Este archivo
```

---

## 🚀 Despliegue paso a paso

### Prerrequisitos

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.7.0
- [Azure CLI](https://learn.microsoft.com/es-es/cli/azure/install-azure-cli) >= 2.60
- Suscripción Azure con cuota aprobada para Azure OpenAI (GPT-4o)
- Permisos: `Contributor` en la suscripción + `User Access Administrator` (para role assignments)

### 1. Autenticarse en Azure

```bash
az login
az account set --subscription "<subscription-id>"
```

### 2. Configurar variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Editar terraform.tfvars con los valores reales
```

Para las variables sensibles se recomienda usar variables de entorno en lugar de escribirlas en el archivo:

```bash
export TF_VAR_openai_api_key="tu-azure-openai-key"
export TF_VAR_mysql_password="contraseña-segura"
export TF_VAR_valid_api_keys='["prod-key-1","prod-key-2"]'
```

### 3. Inicializar Terraform

```bash
terraform init
```

### 4. Revisar el plan

```bash
terraform plan -out=tfplan
```

Revisa que se van a crear ~20 recursos. Los más importantes:
- `azurerm_container_app_environment` — entorno interno en VNet
- `azurerm_container_app` — la API con todas las variables de entorno
- `azurerm_cognitive_account` — Azure OpenAI sin acceso público
- `azurerm_mysql_flexible_server` — MySQL integrado en VNet
- 3× `azurerm_private_endpoint` — OpenAI, ACR, Key Vault
- 4× `azurerm_private_dns_zone` — resolución interna

### 5. Aplicar

```bash
terraform apply tfplan
```

El proceso tarda ~15-20 minutos (MySQL Flexible Server es el más lento).

### 6. Construir y subir la imagen Docker

Usa el valor de `acr_login_server` del output:

```bash
# Obtener el login server del output
ACR=$(terraform output -raw acr_login_server)

# Build y push directamente desde el contexto del repo (sin Docker local)
az acr build \
  --registry ${ACR%%.*} \
  --image agentic-react:$(git rev-parse --short HEAD) \
  --file ../Dockerfile \
  ../
```

### 7. Actualizar el Container App con la nueva imagen

```bash
APP_NAME=$(terraform output -raw container_app_name)
RG=$(terraform output -raw resource_group_name)
ACR=$(terraform output -raw acr_login_server)
TAG=$(git rev-parse --short HEAD)

az containerapp update \
  --name $APP_NAME \
  --resource-group $RG \
  --image $ACR/agentic-react:$TAG
```

### 8. Verificar el despliegue

```bash
# Ver el FQDN interno
terraform output container_app_fqdn

# Ver logs en tiempo real
az containerapp logs show \
  --name $APP_NAME \
  --resource-group $RG \
  --follow

# Health check (desde dentro de la VNet o via VPN/ExpressRoute)
curl https://$(terraform output -raw container_app_fqdn)/health
```

---

## 🔄 CI/CD — GitHub Actions (referencia)

```yaml
# .github/workflows/deploy.yml
name: Deploy to Azure Container Apps

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Azure Login
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Build and push to ACR
        run: |
          az acr build \
            --registry ${{ vars.ACR_NAME }} \
            --image agentic-react:${{ github.sha }} \
            --file Dockerfile .

      - name: Deploy to Container App
        run: |
          az containerapp update \
            --name ${{ vars.CONTAINER_APP_NAME }} \
            --resource-group ${{ vars.RESOURCE_GROUP }} \
            --image ${{ vars.ACR_LOGIN_SERVER }}/agentic-react:${{ github.sha }}
```

---

## 🔧 Rollback de versión

```bash
# Listar revisiones disponibles
az containerapp revision list \
  --name $APP_NAME \
  --resource-group $RG \
  --query "[].{name:name,active:properties.active,created:properties.createdTime}" \
  --output table

# Activar una revisión anterior
az containerapp revision activate \
  --name $APP_NAME \
  --resource-group $RG \
  --revision <nombre-revision-anterior>

# Enviar el 100% del tráfico a esa revisión
az containerapp ingress traffic set \
  --name $APP_NAME \
  --resource-group $RG \
  --revision-weight <nombre-revision-anterior>=100
```

---

## 💡 Consideraciones adicionales para producción

| Aspecto | Recomendación |
|---|---|
| **Estado de Terraform** | Usar backend `azurerm` (Azure Blob Storage) — nunca estado local en producción |
| **MySQL HA** | Cambiar `high_availability.mode` a `ZoneRedundant` |
| **Scaling** | Ajustar `min_replicas = 0` si se tolera cold start; aumentar `max_replicas` según carga |
| **Exposición pública** | Añadir Azure Application Gateway (WAF v2) delante del Container App para tráfico externo |
| **Monitorización** | Habilitar Application Insights y conectarlo al Log Analytics Workspace ya creado |
| **Azure OpenAI quotas** | Solicitar aumento de TPM en el portal si `openai_capacity_tpm = 30` no es suficiente |
| **Secretos en CI/CD** | Nunca pasar `TF_VAR_openai_api_key` como variable en texto plano — usar GitHub Secrets o Azure Key Vault |

---

## 🗑️ Destruir el entorno

```bash
terraform destroy
```

> ⚠️ Key Vault tiene `purge_protection_enabled = true` — si se destruye, el nombre queda reservado 7 días (soft-delete). Ten en cuenta esto al recrear el entorno.

