"""Gerador de dados sintéticos com o mesmo schema do dataset real.

Serve para testes, CI e demonstrações (inclusive de drift) sem depender de rede.
O sinal é plausível, mas NÃO substitui o dataset real para avaliar o modelo.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def make_synthetic(n: int = 5000, seed: int = 42, drift: float = 0.0) -> pd.DataFrame:
    """Gera `n` reservas.

    `drift` > 0 aumenta o lead time (simula mudança de comportamento, útil nos testes de drift).
    """
    rng = np.random.default_rng(seed)

    start = np.datetime64("2015-07-01")
    offsets = rng.integers(0, 790, n)
    dates = pd.to_datetime(start + offsets.astype("timedelta64[D]"))

    lead_time = np.clip(rng.gamma(2.0, 50.0, n) * (1.0 + drift), 0, 700).astype(int)
    hotel = rng.choice(["City Hotel", "Resort Hotel"], n, p=[0.66, 0.34])
    market = rng.choice(
        ["Online TA", "Offline TA/TO", "Direct", "Groups", "Corporate"],
        n,
        p=[0.47, 0.20, 0.12, 0.15, 0.06],
    )
    deposit = rng.choice(["No Deposit", "Non Refund", "Refundable"], n, p=[0.88, 0.115, 0.005])
    prev_canc = rng.choice([0, 1, 2], n, p=[0.93, 0.05, 0.02])
    repeated = rng.choice([0, 1], n, p=[0.97, 0.03])
    parking = rng.choice([0, 1], n, p=[0.94, 0.06])
    requests = np.clip(rng.poisson(0.6, n), 0, 5)
    adr = np.clip(rng.normal(100, 40, n), 20, 400)

    logit = (
        -2.0
        + 0.011 * lead_time
        + 2.5 * (deposit == "Non Refund")
        + 1.2 * (prev_canc > 0)
        - 0.55 * requests
        - 0.8 * parking
        + 0.5 * (market == "Online TA")
        + 0.4 * (hotel == "City Hotel")
        - 0.9 * repeated
        + 0.003 * (adr - 100)
    )
    canceled = (rng.random(n) < _sigmoid(logit)).astype(int)

    reserved = rng.choice(list("ACDEFG"), n, p=[0.6, 0.1, 0.15, 0.08, 0.04, 0.03])
    assigned = np.where(rng.random(n) < 0.1, rng.choice(list("ACDEFG"), n), reserved)

    children = rng.choice([0.0, 1.0, 2.0], n, p=[0.92, 0.05, 0.03])
    children[rng.random(n) < 0.001] = np.nan

    agent = rng.integers(1, 300, n).astype(float)
    agent[rng.random(n) < 0.14] = np.nan
    company = rng.integers(1, 400, n).astype(float)
    company[rng.random(n) < 0.94] = np.nan

    country = rng.choice(
        ["PRT", "GBR", "FRA", "ESP", "DEU", "IRL", "ITA", "BRA"],
        n,
        p=[0.40, 0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.15],
    ).astype(object)
    country[rng.random(n) < 0.01] = None

    df = pd.DataFrame(
        {
            "hotel": hotel,
            "is_canceled": canceled,
            "lead_time": lead_time,
            "arrival_date_year": dates.year.to_numpy(),
            "arrival_date_month": dates.month_name().to_numpy(),
            "arrival_date_week_number": dates.isocalendar().week.to_numpy().astype(int),
            "arrival_date_day_of_month": dates.day.to_numpy(),
            "stays_in_weekend_nights": rng.poisson(0.9, n),
            "stays_in_week_nights": rng.poisson(2.5, n),
            "adults": rng.choice([1, 2, 3], n, p=[0.20, 0.75, 0.05]),
            "children": children,
            "babies": rng.choice([0, 1], n, p=[0.99, 0.01]),
            "meal": rng.choice(["BB", "HB", "SC", "FB"], n, p=[0.75, 0.12, 0.11, 0.02]),
            "country": country,
            "market_segment": market,
            "distribution_channel": rng.choice(
                ["TA/TO", "Direct", "Corporate"], n, p=[0.8, 0.12, 0.08]
            ),
            "is_repeated_guest": repeated,
            "previous_cancellations": prev_canc,
            "previous_bookings_not_canceled": rng.poisson(0.1, n),
            "reserved_room_type": reserved,
            "assigned_room_type": assigned,
            "booking_changes": rng.poisson(0.2, n),
            "deposit_type": deposit,
            "agent": agent,
            "company": company,
            "days_in_waiting_list": np.where(rng.random(n) < 0.03, rng.integers(1, 100, n), 0),
            "customer_type": rng.choice(
                ["Transient", "Contract", "Transient-Party", "Group"], n, p=[0.75, 0.04, 0.20, 0.01]
            ),
            "adr": adr,
            "required_car_parking_spaces": parking,
            "total_of_special_requests": requests,
            "reservation_status": np.where(canceled == 1, "Canceled", "Check-Out"),
            "reservation_status_date": dates.strftime("%Y-%m-%d").to_numpy(),
        }
    )
    return df.sample(frac=1.0, random_state=seed).reset_index(drop=True)
