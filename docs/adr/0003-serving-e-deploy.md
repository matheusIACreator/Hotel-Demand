# ADR 0003: Serving com snapshot versionado e deploy por imagem

- **Status:** aceito
- **Data:** 2026-10-21

## Contexto

O registry local usa SQLite e ficheiros locais. Esses caminhos não estão disponíveis em
Container Apps e não podem ser usados como persistência num container efémero. Não queremos
introduzir um servidor MLflow público sem autenticação nem uma base persistente paga nesta fase.

## Decisão

- `hotelml export` resolve `champion` uma única vez e descarrega a versão explícita para um bundle
  com `manifest.json` (nome, versão e run de origem). Recusa sobrescrever um diretório existente.
- O container inclui esse bundle e carrega o pipeline no arranque, sem acesso ao registry em runtime.
- Sem `MODEL_BUNDLE`, a API local resolve o champion no arranque, também pela versão explícita.
- `/predict` devolve probabilidade, decisão com limiar 0,5 e identificação do modelo. Os pedidos
  aceitam 1 a 100 reservas, sem colunas adicionais, e não são escritos nos logs da aplicação.
- `/health/live` mede disponibilidade do processo; `/health/ready` confirma o carregamento.
  Falha no carregamento impede o arranque da revisão.
- Imagens usam dependências fixadas, utilizador sem privilégios e uma allowlist no contexto Docker.
- CD manual passa primeiro pelo CI, exporta o champion de um MLflow remoto por HTTPS, faz um
  smoke test da imagem, publica no ACR e atualiza Container Apps pelo digest imutável.
- Terraform gere infraestrutura; CD gere a imagem após bootstrap. Estado Terraform continua
  local nesta fase. Um backend remoto com RBAC deve preceder automação de `terraform apply`.

## Consequências

O ADR 0002 continua válido para os aliases no registry. **Alterar aliases não altera processos
nem imagens em execução.** Na API local, reinicie o processo; na Azure, publique o novo snapshot
ou volte à imagem de uma revisão anterior. O runbook descreve ambos os passos.

O primeiro deploy pode ser local, com o registry SQLite. O CD hospedado requer um registry
remoto acessível ao runner e um champion existente, com artefactos que esse runner possa ler.
Este projeto não provisiona esse backend. O CD não treina nem promove modelos automaticamente.

Container Apps escala de zero a uma réplica. ACR Basic e ingestão de logs podem gerar custos
mesmo com a API parada. O orçamento envia alertas; não bloqueia gastos. O exemplo tem ingress
público de demonstração, sem autenticação de clientes; antes de uso externo real, integrar
autenticação e limites de tráfego. Não enviar dados pessoais neste endpoint de demonstração.

## Referências

- [Container Apps e GitHub Actions](https://learn.microsoft.com/en-us/azure/container-apps/github-actions)
- [Recurso Terraform Container App](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/container_app)
- [Budget por resource group](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/consumption_budget_resource_group)

## Complemento: entrega por release aprovada (2026-10-23)

O CD também aceita um bundle publicado como asset de uma release GitHub, identificado por tag,
SHA-256 e versão explícita. Essa alternativa reutiliza o registry local de treino e evita
provisionar MLflow remoto nesta etapa. O workflow verifica o arquivo antes de extrair e aplica
os mesmos testes da imagem e do endpoint. O modo MLflow HTTPS continua disponível.

A release não promove modelos: deve conter um snapshot já aprovado. O digest da imagem e a
imagem anterior ficam registrados no resumo do deploy para rastreabilidade e rollback.
