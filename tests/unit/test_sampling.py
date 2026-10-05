import numpy as np
import pytest
from scipy import stats

from PyFlow import Item, Model
from PyFlow.sampling import (ConstantSampler, ExpressionSampler, SamplerError, ScipySampler,
                             SpecSampler, as_sampler, parse_sampler_spec)

N = 20_000


def draws(spec, n=N, seed=1, **kw):
    s = Model(seed=seed).bind_sampler(spec, "test", **kw)
    return np.array([s.sample() for _ in range(n)])


@pytest.mark.parametrize("spec, mean", [
    ("Constant~7", 7.0),
    ("Uniform~3~7", 5.0),
    ("Normal~10~1", 10.0),
    ("Exponential~0.2", 5.0),        # SimuLean: Exponential takes a RATE
    ("ExponentialMean~5", 5.0),
    ("Triangular~3~5~10", 6.0),
    ("Gamma~2~2.5", 5.0),
    ("Weibull~1~4", 4.0),            # shape 1 == exponential with mean = scale
    ("LogNormal~1~0.5", float(np.exp(1 + 0.125))),
    ("Beta~2~2~10~20", 15.0),
    ("ChiSquare~4", 4.0),
    ("FDistribution~5~20", 20 / 18),
    ("Poisson~3", 3.0),
    ("Binomial~10~0.3", 3.0),
    ("DiscreteUniform~1~6", 3.5),
])
def test_spec_means(spec, mean):
    x = draws(spec)
    se = x.std() / np.sqrt(len(x)) if x.std() > 0 else 0
    assert abs(x.mean() - mean) <= 5 * se + 1e-12


def test_discrete_uniform_is_inclusive():
    assert set(np.unique(draws("DiscreteUniform~1~3", n=2000))) == {1.0, 2.0, 3.0}


def test_normal_spec_truncates_like_simulean():
    x = draws("Normal~0~1", n=2000)
    assert x.min() == 0.0 and (x == 0).mean() > 0.4


def test_student_t_clamp_flag():
    assert draws("StudentT~5", n=2000).min() == 0.0
    s = Model(seed=1).bind_sampler("StudentT~5~false", "t")
    with pytest.raises(SamplerError, match="E_NEGATIVE_SAMPLE"):
        for _ in range(100):
            s.sample()


@pytest.mark.parametrize("bad", ["Expo~1", "Uniform~1", "Uniform~1~2~3", "Exponential~abc",
                                 "Exponential~0", "ChiSquare~2.5", "StudentT~5~maybe"])
def test_invalid_specs_raise(bad):
    with pytest.raises(SamplerError) as exc:
        parse_sampler_spec(bad)
    assert exc.value.code == "E_INVALID_DIST"


def test_label_expression_spec():
    s = parse_sampler_spec("LabelExpression~a * 2 + b")
    assert isinstance(s, ExpressionSampler)
    assert s.sample(Item(0, labels={"a": 3, "b": 1}, item_id=1)) == 7.0


def test_as_sampler_dispatch():
    assert isinstance(as_sampler(3), ConstantSampler)
    assert isinstance(as_sampler(2.5), ConstantSampler)
    assert isinstance(as_sampler(np.float64(1.0)), ConstantSampler)
    assert isinstance(as_sampler("Exponential~1"), SpecSampler)
    assert isinstance(as_sampler("PT1 * 2"), ExpressionSampler)
    assert isinstance(as_sampler(stats.expon(scale=2)), ScipySampler)
    s = ConstantSampler(1)
    assert as_sampler(s) is s
    with pytest.raises(SamplerError):
        as_sampler(True)
    with pytest.raises(SamplerError):
        as_sampler(object())


def test_legacy_get_delay_objects_are_wrapped():
    class Legacy:
        def get_delay(self, item):
            return 4.0

    assert as_sampler(Legacy()).sample() == 4.0


def test_negative_samples_raise_by_default():
    s = Model(seed=1).bind_sampler(stats.norm(loc=0, scale=1), "n")
    with pytest.raises(SamplerError, match="E_NEGATIVE_SAMPLE"):
        for _ in range(100):
            s.sample()


def test_negative_samples_can_be_truncated_explicitly():
    x = draws(stats.norm(loc=0, scale=1), n=500, negative="truncate")
    assert x.min() == 0.0
    with pytest.raises(SamplerError):
        as_sampler(1, negative="clip")


def test_constant_negative_rejected():
    with pytest.raises(SamplerError, match="E_NEGATIVE_SAMPLE"):
        as_sampler(-1).sample()


def test_expression_with_item_methods_and_labels():
    item = Item(0, labels={"tSoldadura": 10, "tInspeccion": 4, "inspeccionOn": 1}, item_id=1)
    legacy = as_sampler("item.get_label_value('tSoldadura') + item.get_label_value('tInspeccion')"
                        " * item.get_label_value('inspeccionOn')")
    direct = as_sampler("tSoldadura + tInspeccion * inspeccionOn")
    assert legacy.sample(item) == direct.sample(item) == 14.0
    assert as_sampler("max(PT, 3)").sample(Item(0, labels={"PT": 1}, item_id=1)) == 3.0


def test_expression_string_labels_are_converted():
    item = Item(0, labels={"PT1": "10"}, item_id=1)
    assert as_sampler("item.get_label_value('PT1')").sample(item) == 10.0


@pytest.mark.parametrize("evil", ["__import__('os').system('echo hi')",
                                  "item.__class__", "open('x')"])
def test_expressions_cannot_escape(evil):
    with pytest.raises(SamplerError, match="E_INVALID_EXPRESSION"):
        as_sampler(evil)


def test_expression_syntax_error():
    with pytest.raises(SamplerError, match="E_INVALID_EXPRESSION"):
        as_sampler("a +* b")


def test_unknown_label_in_expression_is_reported():
    with pytest.raises(SamplerError, match="E_INVALID_EXPRESSION"):
        as_sampler("missing + 1").sample(Item(0, item_id=1))
