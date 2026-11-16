"""Fatos, formato e guardrails da explicação em linguagem natural de uma previsão.

Nada aqui chama um modelo de linguagem. `build_facts` reduz o relatório de fatores ao que o
texto pode afirmar, e `check_explanation` recusa qualquer texto que cite um campo, sentido ou
número fora desses fatos. O texto determinístico de `template_explanation` é o que se mostra
quando a resposta do modelo é recusada.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from hotelml.config import INPUT_COLUMNS

FIELD_LABELS = {
    "hotel": "Hotel",
    "lead_time": "Antecedência da reserva, em dias",
    "arrival_date_month": "Mês de chegada",
    "arrival_date_week_number": "Semana do ano da chegada",
    "arrival_date_day_of_month": "Dia de chegada",
    "stays_in_weekend_nights": "Noites de fim de semana",
    "stays_in_week_nights": "Noites durante a semana",
    "adults": "Adultos",
    "children": "Crianças",
    "babies": "Bebês",
    "meal": "Regime de refeição",
    "country": "País de origem",
    "market_segment": "Segmento de mercado",
    "distribution_channel": "Canal de distribuição",
    "is_repeated_guest": "Hóspede recorrente",
    "previous_cancellations": "Cancelamentos anteriores",
    "previous_bookings_not_canceled": "Reservas anteriores mantidas",
    "reserved_room_type": "Tipo de quarto reservado",
    "booking_changes": "Alterações na reserva",
    "deposit_type": "Tipo de depósito",
    "agent": "Agência",
    "company": "Empresa",
    "days_in_waiting_list": "Dias em lista de espera",
    "customer_type": "Tipo de cliente",
    "adr": "Diária média",
    "required_car_parking_spaces": "Vagas de estacionamento",
    "total_of_special_requests": "Pedidos especiais",
}

# Um fator só entra nos fatos se o efeito for de pelo menos um ponto percentual e superar duas
# vezes o seu erro de amostragem; abaixo disso o sinal pode ser ruído da atribuição.
MIN_EFFECT = 0.01
MAX_FACTORS = 6
LIMITS = {"summary": 500, "text": 320, "caveat": 320}


class FactorStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    direction: Literal["aumenta", "reduz"]
    text: str


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    factors: list[FactorStatement]
    caveat: str


def build_facts(report: dict[str, Any], *, max_factors: int = MAX_FACTORS) -> dict[str, Any]:
    """Reduz o relatório de `hotelml explain` aos fatos que o texto pode usar."""
    if report.get("schema_version") != 1 or report.get("method") != "permutation_shapley":
        raise ValueError("relatório de fatores não suportado")
    if {factor["field"] for factor in report["factors"]} != set(INPUT_COLUMNS):
        raise ValueError("relatório de fatores incompleto")
    relevant = [
        factor
        for factor in report["factors"]
        if abs(factor["contribution"]) >= max(MIN_EFFECT, 2 * factor["std_error"])
    ][:max_factors]
    leading = None
    if len(relevant) == 1:
        leading = relevant[0]["field"]
    elif len(relevant) > 1:
        first, second = relevant[0], relevant[1]
        gap = abs(first["contribution"]) - abs(second["contribution"])
        # Só há um fator principal se a distância para o segundo exceder o erro combinado.
        if gap > 2 * (first["std_error"] ** 2 + second["std_error"] ** 2) ** 0.5:
            leading = first["field"]
    return {
        "probability_pct": round(report["probability"] * 100, 1),
        "baseline_pct": round(report["baseline_probability"] * 100, 1),
        "threshold_pct": round(report["threshold"] * 100, 1),
        "decision": "cancelamento provável" if report["is_canceled"] else "manutenção provável",
        "factors": [
            {
                "field": factor["field"],
                "label": FIELD_LABELS[factor["field"]],
                "value": factor["value"],
                "direction": "aumenta" if factor["contribution"] > 0 else "reduz",
                "effect_pp": round(abs(factor["contribution"]) * 100, 1),
            }
            for factor in relevant
        ],
        "leading_factor": leading,
        "other_fields": len(INPUT_COLUMNS) - len(relevant),
        "model_version": report["model"]["model_version"],
    }


def _number(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _value(value: Any) -> str:
    if value is None:
        return "não informado"
    return str(value).replace(".", ",") if isinstance(value, float) else str(value)


def template_explanation(facts: dict[str, Any]) -> Explanation:
    """Texto fixo montado só com os fatos; usado quando a resposta do modelo é recusada."""
    return Explanation(
        summary=(
            f"O modelo estima {_number(facts['probability_pct'])}% de probabilidade de "
            f"cancelamento para esta reserva, contra {_number(facts['baseline_pct'])}% nas "
            f"reservas típicas do treino. A API classifica a reserva como {facts['decision']}."
        ),
        factors=[
            FactorStatement(
                field=factor["field"],
                direction=factor["direction"],
                text=(
                    f"{factor['label']} ({_value(factor['value'])}) {factor['direction']} a "
                    f"estimativa em {_number(factor['effect_pp'])} pontos percentuais."
                ),
            )
            for factor in facts["factors"]
        ],
        caveat=(
            "Esta é uma estimativa do modelo com base em reservas passadas, não uma certeza "
            "sobre o que vai acontecer."
        ),
    )


NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)?(?![\w]|[.,]\d)")
CERTAINTY = re.compile(
    r"\b(vai|ir[áa]|dever[áa]) (ser )?cancel|com certeza|certamente|sem d[úu]vida"
    r"|definitivamente|inevit[áa]vel",
    re.IGNORECASE,
)
ADVICE = re.compile(
    r"recomend|suger|sugir|entre em contato|o h[óo]spede (pretende|quer|tende|costuma|deve)",
    re.IGNORECASE,
)
# Só o singular afirma um líder; "os que mais pesaram" descreve o grupo e é permitido.
RANKING = re.compile(
    r"principal|pesou mais|\bo (fator |campo |item )?que mais pesou|maior peso|mais importante",
    re.IGNORECASE,
)


def _allowed_numbers(facts: dict[str, Any]) -> set[float]:
    numbers = {
        facts["probability_pct"],
        facts["baseline_pct"],
        facts["threshold_pct"],
        facts["threshold_pct"] / 100,
        float(facts["other_fields"]),
        float(len(facts["factors"])),
    }
    if str(facts["model_version"]).isdigit():
        numbers.add(float(facts["model_version"]))
    for factor in facts["factors"]:
        numbers.add(factor["effect_pp"])
        if isinstance(factor["value"], (int, float)) and not isinstance(factor["value"], bool):
            numbers.add(float(factor["value"]))
    return numbers


def check_explanation(explanation: Explanation, facts: dict[str, Any]) -> list[dict[str, str]]:
    """Violações do texto em relação aos fatos; lista vazia significa que pode ser mostrado."""
    violations: list[dict[str, str]] = []

    def add(code: str, detail: str) -> None:
        violations.append({"code": code, "detail": detail})

    known = {factor["field"]: factor for factor in facts["factors"]}
    cited = [statement.field for statement in explanation.factors]
    for statement in explanation.factors:
        if statement.field not in known:
            add("unknown_field", statement.field)
        elif statement.direction != known[statement.field]["direction"]:
            add("wrong_direction", statement.field)
    if len(cited) != len(set(cited)):
        add("duplicate_field", ", ".join(sorted({f for f in cited if cited.count(f) > 1})))
    if known and not cited:
        add("no_factors", "nenhum fator citado")

    texts = {"summary": explanation.summary, "caveat": explanation.caveat}
    texts |= {f"factors[{i}].text": s.text for i, s in enumerate(explanation.factors)}
    allowed = _allowed_numbers(facts)
    for location, text in texts.items():
        limit = LIMITS["text" if location.startswith("factors") else location]
        if not text.strip() or len(text) > limit:
            add("length", location)
        for match in NUMBER.findall(text):
            if not any(abs(float(match.replace(",", ".")) - number) < 1e-6 for number in allowed):
                add("number_not_in_facts", f"{location}: {match}")
        if CERTAINTY.search(text):
            add("certainty_claim", location)
        if ADVICE.search(text):
            add("advice_or_intent", location)

    leading = facts["leading_factor"]
    for index, statement in enumerate(explanation.factors):
        if RANKING.search(statement.text) and statement.field != leading:
            add("unsupported_ranking", f"factors[{index}].text")
    if leading is None and RANKING.search(explanation.summary):
        add("unsupported_ranking", "summary")
    if not re.search(r"estimativ|certeza|incerteza", explanation.caveat, re.IGNORECASE):
        add("missing_caveat", "caveat")
    return violations
