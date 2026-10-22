import card from "@/lib/data/model-card.json"

export const MODEL_CARD = card

export type MetricKey = keyof typeof card.metrics

export const METRIC_INFO: Record<
  MetricKey,
  { label: string; better: "maior" | "menor"; description: string }
> = {
  roc_auc: {
    label: "ROC AUC",
    better: "maior",
    description:
      "Capacidade de ordenar reservas canceladas acima das mantidas. 0,5 equivale ao acaso.",
  },
  pr_auc: {
    label: "PR AUC (average precision)",
    better: "maior",
    description:
      "Precisão média ao longo dos limiares. A referência de um classificador aleatório é a taxa de cancelamento do teste.",
  },
  f1: {
    label: "F1",
    better: "maior",
    description:
      "Equilíbrio entre precisão e recall da classe cancelada, com o limiar 0,5.",
  },
  accuracy: {
    label: "Acurácia",
    better: "maior",
    description:
      "Proporção de reservas classificadas corretamente, com o limiar 0,5.",
  },
  brier: {
    label: "Brier",
    better: "menor",
    description:
      "Erro quadrático médio das probabilidades; indica a qualidade da calibração.",
  },
  log_loss: {
    label: "Log loss",
    better: "menor",
    description: "Penaliza probabilidades confiantes que se revelam erradas.",
  },
}

// Nome do estimador a partir de `model_type` (ver DEFAULT_PARAMS em src/hotelml/features.py).
export const ESTIMATORS: Record<string, string> = {
  hgb: "HistGradientBoostingClassifier (scikit-learn)",
  logreg: "LogisticRegression (scikit-learn)",
}

export function daysBetween(a: string, b: string): number {
  return (Date.parse(b) - Date.parse(a)) / 86_400_000
}
