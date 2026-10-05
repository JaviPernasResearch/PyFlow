"""Stochastic standard lines checked against queueing theory.

Each check runs independent seeded replications (with warm-up) and asserts that the
theoretical value lies inside the 99 % confidence interval of the replication means.
"""
import math

import numpy as np
from scipy import stats

from PyFlow.standard_lines import single_station

REPLICATIONS = 10
HORIZON = 20_000
WARMUP = 2_000


def replicate(build, metric):
    values = []
    for rep in range(REPLICATIONS):
        line = build(seed=1000 + rep)
        values.append(metric(line.run(HORIZON, warmup=WARMUP)))
    return np.array(values)


def assert_in_ci(values, expected, level=0.99):
    mean = values.mean()
    half = stats.t.ppf(0.5 + level / 2, len(values) - 1) * values.std(ddof=1) / math.sqrt(len(values))
    assert mean - half <= expected <= mean + half, f"{expected} not in {mean:.4f} ± {half:.4f}"


def erlang_c_lq(lam, mu, c):
    a, rho = lam / mu, lam / (c * mu)
    p0 = 1 / (sum(a**k / math.factorial(k) for k in range(c)) + a**c / (math.factorial(c) * (1 - rho)))
    return a**c / (math.factorial(c) * (1 - rho)) * p0 * rho / (1 - rho)


def lq(r):
    return r["elements"]["Q1"]["wip_average"]


def wq(r):
    return r["elements"]["Q1"]["staytime_average"]


def util(r):
    return r["elements"]["M1"]["utilization"]


def test_mm1():
    lam, mu = 0.8, 1.0
    rho = lam / mu

    def build(seed):
        return single_station(arrival=f"Exponential~{lam}", service=f"Exponential~{mu}", seed=seed)

    assert_in_ci(replicate(build, util), rho)
    assert_in_ci(replicate(build, lq), rho**2 / (1 - rho))
    assert_in_ci(replicate(build, wq), rho / (mu - lam))


def test_mmc_erlang_c():
    lam, mu, c = 1.6, 1.0, 2

    def build(seed):
        return single_station(arrival=f"Exponential~{lam}", service=f"Exponential~{mu}", servers=c, seed=seed)

    expected_lq = erlang_c_lq(lam, mu, c)
    assert_in_ci(replicate(build, lq), expected_lq)
    assert_in_ci(replicate(build, wq), expected_lq / lam)
    assert_in_ci(replicate(build, util), lam / (c * mu))


def test_md1_pollaczek_khinchine():
    lam, d = 0.8, 1.0
    rho = lam * d

    def build(seed):
        return single_station(arrival=f"Exponential~{lam}", service=d, seed=seed)

    assert_in_ci(replicate(build, lq), rho**2 / (2 * (1 - rho)))


def test_little_law_holds_per_replication():
    """L = lambda * W for the whole station (queue + server), on every replication."""
    for rep in range(3):
        r = single_station(arrival="Exponential~0.8", service="Exponential~1", seed=rep).run(HORIZON, warmup=WARMUP)
        e = r["elements"]
        L = e["Q1"]["wip_average"] + e["M1"]["wip_average"]
        W = e["Q1"]["staytime_average"] + e["M1"]["staytime_average"]
        assert math.isclose(L, r["throughput"] * W, rel_tol=0.02)
