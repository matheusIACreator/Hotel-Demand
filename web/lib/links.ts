export const REPO_URL = "https://github.com/matheusIACreator/Hotel-Demand"

export const repoFile = (path: string) => `${REPO_URL}/blob/main/${path}`

export const DOCS = {
  adrDataset: repoFile("docs/adr/0001-dataset-e-vazamento.md"),
  adrRegistry: repoFile("docs/adr/0002-registry-por-aliases.md"),
  adrServing: repoFile("docs/adr/0003-serving-e-deploy.md"),
  adrSpark: repoFile("docs/adr/0004-pipelines-spark.md"),
  runbookDeploy: repoFile("docs/runbooks/deploy-azure.md"),
  runbookRollback: repoFile("docs/runbooks/rollback.md"),
  runbookPipelines: repoFile("docs/runbooks/pipelines-spark.md"),
  readme: repoFile("README.md"),
  ciWorkflow: repoFile(".github/workflows/ci.yml"),
  deployWorkflow: repoFile(".github/workflows/deploy.yml"),
  terraform: repoFile("infra/main.tf"),
} as const
