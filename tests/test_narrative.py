from __future__ import annotations

import copy

import pytest

from hotelml.config import INPUT_COLUMNS
from hotelml.narrative import (
    FIELD_LABELS,
    Explanation,
    build_facts,
    check_explanation,
    template_explanation,
)


def report(contributions: dict[str, tuple[float, float]], probability=0.84, baseline=0.359):
    """Relatório mínimo de `hotelml explain`: campo -> (contribuição, erro padrão)."""
    values = {"lead_time": 104, "adr": 119.586, "market_segment": "Online TA", "company": None}
    factors = [
        {
            "field": name,
            "value": values.get(name, 0),
            "contribution": contributions.get(name, (0.0, 0.0))[0],
            "std_error": contributions.get(name, (0.0, 0.0))[1],
        }
        for name in INPUT_COLUMNS
    ]
    factors.sort(key=lambda factor: -abs(factor["contribution"]))
    return {
        "schema_version": 1,
        "method": "permutation_shapley",
        "model": {"model_name": "hotel", "model_version": "1", "run_id": "run"},
        "threshold": 0.5,
        "probability": probability,
        "is_canceled": probability >= 0.5,
        "baseline_probability": baseline,
        "factors": factors,
    }


@pytest.fixture
def facts():
    return build_facts(
        report(
            {
                "market_segment": (0.1464, 0.0086),
                "lead_time": (0.0965, 0.006),
                "adr": (0.0854, 0.0048),
                "company": (-0.03, 0.004),
            }
        )
    )


def explanation(**changes) -> Explanation:
    base = {
        "summary": (
            "O modelo estima 84,0% de probabilidade de cancelamento, acima dos 35,9% das "
            "reservas típicas. A API classifica a reserva como cancelamento provável."
        ),
        "factors": [
            {
                "field": "market_segment",
                "direction": "aumenta",
                "text": "A reserva veio por agência online, o fator que mais pesou: "
                "14,6 pontos percentuais a mais.",
            },
            {
                "field": "lead_time",
                "direction": "aumenta",
                "text": "A antecedência de 104 dias aumenta a estimativa em 9,7 pontos.",
            },
            {
                "field": "company",
                "direction": "reduz",
                "text": "Não haver empresa associada reduz a estimativa em 3,0 pontos.",
            },
        ],
        "caveat": "É uma estimativa do modelo com base em reservas passadas, não uma certeza.",
    }
    return Explanation.model_validate(base | changes)


def codes(text: Explanation, facts) -> list[str]:
    return [violation["code"] for violation in check_explanation(text, facts)]


def test_every_contract_field_has_a_label():
    assert set(FIELD_LABELS) == set(INPUT_COLUMNS)


def test_facts_keep_only_clear_effects_rounded_and_labeled(facts):
    assert facts["probability_pct"] == 84.0 and facts["baseline_pct"] == 35.9
    assert facts["threshold_pct"] == 50.0 and facts["decision"] == "cancelamento provável"
    assert [f["field"] for f in facts["factors"]] == [
        "market_segment",
        "lead_time",
        "adr",
        "company",
    ]
    assert facts["factors"][0] == {
        "field": "market_segment",
        "label": "Segmento de mercado",
        "value": "Online TA",
        "direction": "aumenta",
        "effect_pp": 14.6,
    }
    assert facts["factors"][2]["value"] == 119.59  # 119,586 na reserva
    assert facts["factors"][3]["direction"] == "reduz" and facts["factors"][3]["value"] is None
    assert facts["other_fields"] == len(INPUT_COLUMNS) - 4
    # 14,6 contra 9,7 com erros pequenos: o primeiro destaca-se com folga.
    assert facts["leading_factor"] == "market_segment"


def test_noise_and_small_effects_never_become_factors():
    facts = build_facts(
        report(
            {
                "lead_time": (0.05, 0.004),
                "adr": (0.009, 0.001),  # abaixo de um ponto percentual
                "adults": (0.04, 0.03),  # dentro de duas vezes o erro
            },
            probability=0.3,
        )
    )
    assert [f["field"] for f in facts["factors"]] == ["lead_time"]
    assert facts["decision"] == "manutenção provável" and facts["leading_factor"] == "lead_time"
    empty = build_facts(report({}))
    assert empty["factors"] == [] and empty["leading_factor"] is None


def test_close_factors_have_no_leader_and_the_list_is_capped():
    close = build_facts(report({"lead_time": (0.1464, 0.0086), "adr": (0.1364, 0.0069)}))
    assert close["leading_factor"] is None
    many = {name: (0.02 + index / 1000, 0.001) for index, name in enumerate(INPUT_COLUMNS[:9])}
    assert len(build_facts(report(many))["factors"]) == 6


def test_unsupported_reports_are_rejected():
    for change in ({"schema_version": 2}, {"method": "outro"}):
        with pytest.raises(ValueError, match="não suportado"):
            build_facts(report({}) | change)
    partial = report({})
    partial["factors"] = partial["factors"][:5]
    with pytest.raises(ValueError, match="incompleto"):
        build_facts(partial)


def test_grounded_explanation_and_template_pass(facts):
    assert check_explanation(explanation(), facts) == []
    # O texto fixo é o que se mostra numa recusa: tem de passar nos mesmos guardrails.
    template = template_explanation(facts)
    assert check_explanation(template, facts) == []
    assert "119,59" in template.factors[2].text and "não informado" in template.factors[3].text
    empty = build_facts(report({}))
    assert check_explanation(template_explanation(empty), empty) == []


@pytest.mark.parametrize(
    "change,code",
    [
        (
            {"summary": "O modelo estima 84,0% e 70% dos casos assim cancelam."},
            "number_not_in_facts",
        ),
        ({"summary": "Com 84,0%, contra cerca de 36% no geral."}, "number_not_in_facts"),
        ({"summary": "Com 84,0%, esta reserva vai ser cancelada."}, "certainty_claim"),
        ({"summary": "Com 84,0%, certamente haverá cancelamento."}, "certainty_claim"),
        ({"summary": "Com 84,0%, recomendamos ligar para o cliente."}, "advice_or_intent"),
        ({"summary": "Com 84,0%, o hóspede pretende desistir."}, "advice_or_intent"),
        ({"caveat": "Os dados são de reservas passadas."}, "missing_caveat"),
        ({"caveat": " "}, "length"),
        ({"summary": "84,0% " + "muito " * 100}, "length"),
        ({"factors": []}, "no_factors"),
    ],
)
def test_ungrounded_text_is_flagged(facts, change, code):
    assert code in codes(explanation(**change), facts)


def test_factors_must_match_fields_directions_and_ranking(facts):
    base = explanation().model_dump()["factors"]

    def with_factor(index: int, **change):
        factors = copy.deepcopy(base)
        factors[index] |= change
        return explanation(factors=factors)

    assert codes(with_factor(1, field="country"), facts) == ["unknown_field"]
    assert codes(with_factor(1, direction="reduz"), facts) == ["wrong_direction"]
    assert "duplicate_field" in codes(with_factor(1, field="market_segment"), facts)
    # Um campo fora dos fatos traz também um número que os fatos não têm.
    invented = with_factor(1, field="adults", text="Ter 2 adultos aumenta a estimativa.")
    assert set(codes(invented, facts)) == {"unknown_field", "number_not_in_facts"}
    ranked = with_factor(1, text="A antecedência de 104 dias é o principal fator.")
    assert codes(ranked, facts) == ["unsupported_ranking"]


def test_ranking_needs_a_clear_leader(facts):
    tied = facts | {"leading_factor": None}
    assert codes(explanation(), tied) == ["unsupported_ranking"]
    summary = "O modelo estima 84,0%; o que mais pesou foi o canal de venda."
    assert "unsupported_ranking" in codes(explanation(summary=summary), tied)
    assert "unsupported_ranking" not in codes(explanation(summary=summary), facts)
    # Descrever o grupo, sem eleger um líder, é a formulação pedida no prompt.
    group = "O modelo estima 84,0%; estes foram os fatores que mais pesaram."
    factors = explanation().model_dump()["factors"]
    factors[0]["text"] = "A reserva veio por agência online: 14,6 pontos percentuais a mais."
    assert codes(explanation(summary=group, factors=factors), tied) == []
    # O mesmo número escrito sem a casa decimal continua a ser o número dos fatos.
    assert codes(explanation(summary="O modelo estima 84% de probabilidade."), facts) == []
