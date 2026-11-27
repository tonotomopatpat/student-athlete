import pytest

from app.ml import bkt
from app.ml.bkt import BKTParams

PARAMS = BKTParams(p_l0=0.2, p_t=0.15, p_g=0.25, p_s=0.10)


def test_single_correct_response_matches_hand_calculation():
    # posterior = 0.18 / (0.18 + 0.8 * 0.25) = 0.47368; then + (1 - 0.47368) * 0.15
    assert bkt.trace([True], PARAMS)[0] == pytest.approx(0.552632, abs=1e-6)


def test_single_incorrect_response_matches_hand_calculation():
    # posterior = 0.02 / (0.02 + 0.8 * 0.75) = 0.032258; then + (1 - 0.032258) * 0.15
    assert bkt.trace([False], PARAMS)[0] == pytest.approx(0.177419, abs=1e-6)


def test_correct_answers_increase_mastery_and_reach_threshold():
    estimates = bkt.trace([True] * 8, PARAMS)
    assert estimates == sorted(estimates)
    assert bkt.is_mastered(estimates[-1])


def test_incorrect_answer_lowers_estimate():
    before = 0.7
    assert bkt.update(before, False, PARAMS) < before


def test_estimates_stay_within_bounds_for_mixed_sequence():
    sequence = [True, False, False, True, True, False, True, True, True, False]
    assert all(0.0 < p < 1.0 for p in bkt.trace(sequence, PARAMS))


def test_start_value_overrides_prior():
    assert bkt.trace([True], PARAMS, p_start=0.9)[0] > bkt.trace([True], PARAMS)[0]


def test_predict_correct_blends_slip_and_guess():
    assert bkt.predict_correct(1.0, PARAMS) == pytest.approx(0.9)
    assert bkt.predict_correct(0.0, PARAMS) == pytest.approx(0.25)


@pytest.mark.parametrize("kwargs", [{"p_l0": 0.0}, {"p_t": 1.0}, {"p_g": 0.6, "p_s": 0.5}, {"p_s": -0.1}])
def test_invalid_parameters_are_rejected(kwargs):
    with pytest.raises(ValueError):
        BKTParams(**kwargs)
