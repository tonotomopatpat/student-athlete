import random

import pytest

from app.ml import qlearning as ql


def test_bucket_boundaries():
    assert [ql.mastery_bucket(p) for p in (0.0, 0.29, 0.3, 0.59, 0.6, 0.84, 0.85, 0.99)] == [0, 0, 1, 1, 2, 2, 3, 3]
    assert [ql.urgency_bucket(d) for d in (None, 30, 7.1, 7, 2.1, 2, 0)] == [0, 0, 0, 1, 1, 2, 2]
    assert [ql.time_bucket(m) for m in (0, 19, 20, 44, 45, 200)] == [0, 0, 1, 1, 2, 2]
    assert [ql.recency_bucket(h) for h in (None, 0, 47, 48, 500)] == [0, 1, 1, 2, 2]


def test_state_key_format():
    assert ql.make_state(0.1, None, 60, None) == "m0-u0-t2-r0"


def test_eligibility_depends_on_time_and_content():
    assert ql.eligible_actions(10, True, 20) == []
    assert ql.eligible_actions(15, True, 20) == ["review_material"]
    assert ql.eligible_actions(60, False, 20) == ["practice", "quiz"]
    assert ql.eligible_actions(60, True, 2) == ["review_material"]
    assert ql.eligible_actions(60, True, 4) == ["review_material", "practice", "revisit"]
    assert set(ql.eligible_actions(60, True, 20)) == set(ql.ACTIONS)


def test_greedy_choice_follows_prior_when_untrained():
    learner = ql.QLearner(epsilon=0.0)
    rng = random.Random(1)
    assert learner.select("m0-u0-t2-r0", list(ql.ACTIONS), rng) == ("revisit", False)
    assert learner.select("m3-u0-t2-r0", list(ql.ACTIONS), rng) == ("quiz", False)


def test_selection_never_returns_ineligible_action():
    learner = ql.QLearner(epsilon=1.0)
    rng = random.Random(3)
    for _ in range(100):
        action, explored = learner.select("m1-u0-t1-r0", ["practice", "review_material"], rng)
        assert action in ("practice", "review_material")
        assert explored


def test_update_matches_q_learning_formula():
    learner = ql.QLearner(alpha=0.15, gamma=0.8)
    state, nxt = "m0-u0-t2-r0", "m1-u0-t2-r1"
    new_value = learner.update(state, "revisit", 1.0, nxt, ["practice", "revisit"])
    # q = 0.8 prior; target = 1 + 0.8 * max(next priors: practice 0.6, revisit 0.6) = 1.48
    assert new_value == pytest.approx(0.8 + 0.15 * (1.48 - 0.8))
    assert learner.visits[(state, "revisit")] == 1


def test_repeated_positive_rewards_raise_value_toward_target():
    learner = ql.QLearner()
    state = "m1-u0-t1-r1"
    values = [learner.update(state, "practice", 1.0, state, ["practice"]) for _ in range(30)]
    assert values == sorted(values)


def test_reward_uses_only_observed_mastery_change():
    assert ql.compute_reward(0.4, 0.4, skipped=False) == pytest.approx(0.1)
    assert ql.compute_reward(0.4, 0.6, skipped=False) == pytest.approx(0.9)
    assert ql.compute_reward(0.6, 0.4, skipped=False) < 0.1
    assert ql.compute_reward(0.4, 0.9, skipped=True) == -0.2
    assert ql.compute_reward(0.0, 1.0, skipped=False) == 2.0
