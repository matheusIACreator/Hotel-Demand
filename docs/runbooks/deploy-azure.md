# Deploy da API na Azure

## Preparar e validar localmente (PowerShell)

Executar na raiz do projeto. Python 3.12 é a versão usada no CI e no container.

```powershell
py -3.12 -m venv .venv
.venv/Scripts/Activate.ps1
pip install -r requirements-dev.lock
pip install --no-deps -e .
ruff check src tests scripts
ruff format --check src tests scripts
mypy src
pytest --cov=hotelml --cov-fail-under=80
hotelml train --source hf
hotelml export --output model-bundle
uvicorn hotelml.api:app --host 127.0.0.1 --port 8000
```

Sem `MODEL_BUNDLE`, a API carrega o champion do registry no arranque. Para testar o snapshot,
defina `$env:MODEL_BUNDLE='./model-bundle'` antes de iniciar. O Swagger fica em
`http://127.0.0.1:8000/docs`. Numa segunda consola, com o ambiente ativado:

```powershell
$version = (Get-Content model-bundle/manifest.json | ConvertFrom-Json).model_version
python scripts/smoke_api.py http://127.0.0.1:8000 --version $version
docker build -t hotelml:local .
docker run --rm -p 8001:8000 hotelml:local
# Noutra consola:
python scripts/smoke_api.py http://127.0.0.1:8001 --version $version
```

Para exportar outra versão, escolha outro diretório e arquive o anterior fora do contexto de
build; a imagem usa sempre `model-bundle/`. Nunca incluir `.env`, SQLite ou dataset na imagem.
Para atualizar dependências, use `uv pip compile` para ambos os locks e volte a validar treino,
carregamento e container. Não altere só as versões do container: sklearn requer compatibilidade
com as dependências do treino.

## Bootstrap da infraestrutura

Requer Azure CLI autenticada, Terraform >=1.9 e Docker ativo. A identidade que aplica precisa
criar recursos, atribuir `AcrPull` e gerir budgets. Registe os resource providers requeridos se a
subscrição ainda não os tiver ativos. O provider está configurado para registar apenas os
namespaces necessários, incluindo `Microsoft.App`, em vez do conjunto legacy do AzureRM 4.
Esse registo pode atrasar o primeiro `plan`, sem criar os recursos do laboratório.
O orçamento usa a moeda de faturação, não assume USD.

O exemplo usa North Europe. A Microsoft restringe West Europe para novos clientes
([erro de elegibilidade regional](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-region-access-policy)).
Se uma aplicação parcial já criou o grupo em outra região, preserve a sua localização com
`resource_group_location = "westeurope"` e altere `location` para a região dos serviços.
Reveja o novo plano: mudar a região dos metadados do grupo implica substituição, enquanto
esta separação permite conservar o grupo e o orçamento. Não altere o estado manualmente.

```powershell
az login
az account set --subscription '<subscription-id>'
Copy-Item infra/example.tfvars infra/terraform.tfvars
# Editar IDs, ACR único, email e primeiro dia do mês atual em terraform.tfvars.
terraform -chdir=infra init
terraform -chdir=infra plan -out=bootstrap.tfplan
terraform -chdir=infra apply bootstrap.tfplan
$acr = terraform -chdir=infra output -raw registry_name
$server = terraform -chdir=infra output -raw registry_login_server
az acr login --name $acr
docker tag hotelml:local "${server}/hotelml:bootstrap"
docker push "${server}/hotelml:bootstrap"
```

Obtenha o digest da imagem publicada e coloque `image = "<server>/hotelml@sha256:<digest>"`
em `infra/terraform.tfvars`. Depois:

```powershell
terraform -chdir=infra plan -out=api.tfplan
terraform -chdir=infra apply api.tfplan
$url = terraform -chdir=infra output -raw api_url
python scripts/smoke_api.py $url --version $version
```

O primeiro apply cria ACR, ambiente, identidade, logs e budget; o segundo cria a API.
A propagação inicial de RBAC pode demorar; se o pull falhar por autorização, confirme `AcrPull`
e repita o apply após a propagação. Preserve o estado local e os ficheiros de lock. Não use
`image=""` depois de criar a API: isso remove o recurso no próximo apply.

## Configurar CD no GitHub

O repositório já tem `origin`. Publique as alterações e configure um environment `azure-dev`,
restrito à branch `main`, com revisão obrigatória se desejada. Configure uma aplicação/identidade
Entra com credencial federada para:

```text
issuer: https://token.actions.githubusercontent.com
subject: repo:matheusIACreator/Hotel-Demand:environment:azure-dev
audience: api://AzureADTokenExchange
```

Conceda à identidade do CD `AcrPush` no ACR e `Container Apps Contributor` no resource group.
Para `az acr show`, conceda também `Reader` no ACR. A aplicação usa uma identidade separada
com apenas `AcrPull`; não há password de administrador do ACR nem client secret Azure no CI.

Variáveis do environment:

| Nome | Valor |
| --- | --- |
| `AZURE_CLIENT_ID` | Client ID da identidade federada |
| `AZURE_TENANT_ID` | Tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Subscrição |
| `AZURE_RESOURCE_GROUP` | Output `resource_group` |
| `AZURE_APP_NAME` | Output `app_name` |
| `ACR_NAME` | Output `registry_name` |
| `MLFLOW_TRACKING_URI` | Registry remoto por HTTPS, acessível ao runner |
| `MODEL_NAME` | `hotel-cancellation` |

Secrets opcionais, conforme autenticação do MLflow: `MLFLOW_TRACKING_USERNAME`,
`MLFLOW_TRACKING_PASSWORD` ou `MLFLOW_TRACKING_TOKEN`. O backend deve disponibilizar os
artefactos pelo servidor/proxy ou por storage acessível ao runner. Um caminho local do seu PC
não serve no GitHub Actions. SQLite e servidor MLflow remoto não são criados por este Terraform.

Execute manualmente **Deploy Azure** na branch `main`. O workflow executa CI, exporta o champion,
valida o container, publica a imagem e valida o endpoint real. Um smoke test falhado marca o
deploy como falhado; não faz rollback automático. Consulte o runbook de rollback.

## Custos e encerramento

O budget alerta a 50%, 80% e 100%; não interrompe recursos nem garante preservar o crédito.
ACR e logs têm custos independentes da escala a zero. Confirme os alertas no portal e acompanhe
Cost Management. Para encerrar o laboratório, reveja `terraform -chdir=infra plan -destroy` e
depois execute `terraform -chdir=infra destroy`, aceitando a remoção dos recursos e imagens.

## Bundle aprovado em uma release (sem MLflow remoto)

O CD aceita duas origens: o champion de um MLflow HTTPS ou um bundle aprovado em uma release
GitHub deste repositório. A segunda opção permite usar o registry local no treino e publicar
somente o snapshot, sem provisionar um servidor MLflow.

1. Exporte o champion para `model-bundle/` e valide o container local com `scripts/smoke_api.py`.
2. Empacote apenas o modelo e o manifesto:

   ```powershell
   python scripts/model_release.py pack --output model-bundle.tar.gz
   ```

   Anote o SHA-256 exibido. Publique `model-bundle.tar.gz` como asset de uma release identificada
   por uma tag única (por exemplo `model-v1`). Não substitua assets de uma release aprovada.
3. Execute **Deploy Azure** na `main`, preenchendo `model_release`, `model_sha256` e
   `model_version`. O workflow baixa o asset do próprio repositório, verifica o checksum, a
   versão e os caminhos antes de extrair e construir a imagem. O smoke test confirma que o
   modelo carrega e responde antes de publicar.

Nesse modo, as variáveis/secrets MLflow são dispensáveis; OIDC e as variáveis Azure continuam
obrigatórias. Checksum e versão devem vir da aprovação do bundle, não de um arquivo baixado
junto com ele. O resumo do deploy registra também a imagem anterior para rollback.

## Frontend e CI

Na Vercel, configure Root Directory `web`, framework Next.js e Production Branch `main`.
`HOTELML_API_URL` deve existir em Production e Preview. Branches e PRs geram previews; `main`
publica em produção pela integração Git. O CI GitHub verifica separadamente o frontend.

O grupo de concorrência do CI inclui o nome do workflow: uma execução comum de CI não cancela
as verificações chamadas pelo deploy. Falhas end-to-end preservam os traces por sete dias.
