"""Simulated-learner environment for pretraining and comparing recommendation policies.

Everything here is SIMULATION. The effect of each activity type on a simulated
learner (EnvParams) is an assumption, not an empirical finding. Results show how
policies behave under those assumptions, not how real student-athletes learn.
Training and evaluation use different EnvParams so that a policy is not scored
only on the dynamics it was trained on.
"""

import json
import math
import random
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.ml import bkt
from app.ml.qlearning import (
    ACTIONS,
    ACTIVITY_MINUTES,
    ACTIVITY_QUESTIONS,
    QLearner,
    compute_reward,
    eligible_actions,
    make_state,
    prior_q,
)

DAILY_MINUTES_CHOICES = [0, 20, 30, 45, 60, 90]
DAILY_MINUTES_WEIGHTS = [0.15, 0.15, 0.20, 0.20, 0.20, 0.10]
SIM_BKT = bkt.BKTParams()


@dataclass(frozen=True)
class EnvParams:
    """Probability that a learner who does not yet know a topic learns it from one activity."""

    learn_prob: dict[str, float]
    daily_forgetting: float = 0.01


ENV_TRAIN = EnvParams({"review_material": 0.12, "practice": 0.10, "quiz": 0.06, "revisit": 0.25})
ENV_EVAL_SHIFTED = EnvParams({"review_material": 0.08, "practice": 0.14, "quiz": 0.08, "revisit": 0.20})
ENV_EVAL_PRACTICE_HEAVY = EnvParams({"review_material": 0.05, "practice": 0.20, "quiz": 0.10, "revisit": 0.15})
EVAL_ENVS = {"train_env": ENV_TRAIN, "shifted_env": ENV_EVAL_SHIFTED, "practice_heavy_env": ENV_EVAL_PRACTICE_HEAVY}


@dataclass
class SimStudent:
    topics: int
    rng: random.Random
    known: list[bool] = field(init=False)
    estimate: list[float] = field(init=False)
    last_activity_day: list[int | None] = field(init=False)
    guess: float = field(init=False)
    slip: float = field(init=False)

    def __post_init__(self) -> None:
        self.known = [self.rng.random() < SIM_BKT.p_l0 for _ in range(self.topics)]
        self.estimate = [SIM_BKT.p_l0] * self.topics
        self.last_activity_day = [None] * self.topics
        self.guess = self.rng.uniform(0.15, 0.30)
        self.slip = self.rng.uniform(0.05, 0.15)


Policy = Callable[[str, list[str], "SimStudent"], str]


def _pick_topic(student: SimStudent) -> int | None:
    candidates = [i for i, p in enumerate(student.estimate) if not bkt.is_mastered(p)]
    if not candidates:
        return None
    lowest = min(student.estimate[i] for i in candidates)
    return student.rng.choice([i for i in candidates if student.estimate[i] == lowest])


def _apply_activity(student: SimStudent, topic: int, action: str, env: EnvParams) -> None:
    if not student.known[topic] and student.rng.random() < env.learn_prob[action]:
        student.known[topic] = True
    for _ in range(ACTIVITY_QUESTIONS[action]):
        p_correct = (1.0 - student.slip) if student.known[topic] else student.guess
        correct = student.rng.random() < p_correct
        student.estimate[topic] = bkt.update(student.estimate[topic], correct, SIM_BKT)


def run_student(policy: Policy, env: EnvParams, seed: int, topics: int = 5, days: int = 28,
                learner: QLearner | None = None, learner_rng: random.Random | None = None) -> dict[str, float]:
    rng = random.Random(seed)
    student = SimStudent(topics, rng)
    known_start = sum(student.known)
    minutes_used = 0
    for day in range(days):
        for i in range(topics):
            if student.known[i] and rng.random() < env.daily_forgetting:
                student.known[i] = False
        remaining = rng.choices(DAILY_MINUTES_CHOICES, DAILY_MINUTES_WEIGHTS)[0]
        for _ in range(2):
            topic = _pick_topic(student)
            if topic is None:
                break
            eligible = eligible_actions(remaining, True, 20)
            if not eligible:
                break
            last = student.last_activity_day[topic]
            hours_since = None if last is None else (day - last) * 24.0
            state = make_state(student.estimate[topic], None, remaining, hours_since)
            action = policy(state, eligible, student)
            before = student.estimate[topic]
            _apply_activity(student, topic, action, env)
            student.last_activity_day[topic] = day
            remaining -= ACTIVITY_MINUTES[action]
            minutes_used += ACTIVITY_MINUTES[action]
            if learner is not None:
                reward = compute_reward(before, student.estimate[topic], skipped=False)
                next_state = make_state(student.estimate[topic], None, remaining + ACTIVITY_MINUTES[action], 0.0)
                next_eligible = eligible_actions(remaining + ACTIVITY_MINUTES[action], True, 20)
                learner.update(state, action, reward, next_state, next_eligible)
    return {
        "known_end": float(sum(student.known)),
        "estimated_mastery": statistics.fmean(student.estimate),
        "minutes": float(minutes_used),
        "known_start": float(known_start),
    }


def random_policy(rng: random.Random) -> Policy:
    return lambda state, eligible, student: rng.choice(eligible)


def fixed_sequence_policy() -> Policy:
    pointers: dict[int, int] = {}

    def choose(state: str, eligible: list[str], student: SimStudent) -> str:
        key = id(student)
        for _ in range(len(ACTIONS)):
            action = ACTIONS[pointers.get(key, 0) % len(ACTIONS)]
            pointers[key] = pointers.get(key, 0) + 1
            if action in eligible:
                return action
        return eligible[0]

    return choose


def mastery_rule_policy() -> Policy:
    return lambda state, eligible, student: max(eligible, key=lambda a: prior_q(state, a))


def qlearning_policy(learner: QLearner, rng: random.Random, explore: bool) -> Policy:
    return lambda state, eligible, student: learner.select(state, eligible, rng, explore=explore)[0]


def pretrain(env: EnvParams = ENV_TRAIN, students: int = 3000, seed: int = 7, epsilon: float = 0.2) -> QLearner:
    learner = QLearner(epsilon=epsilon)
    rng = random.Random(seed)
    policy = qlearning_policy(learner, rng, explore=True)
    for i in range(students):
        run_student(policy, env, seed=seed * 100_000 + i, learner=learner)
    learner.epsilon = QLearner().epsilon
    return learner


def _summarize(values: list[float]) -> dict[str, float]:
    mean = statistics.fmean(values)
    se = statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return {"mean": round(mean, 4), "ci95": round(1.96 * se, 4)}


def compare_policies(trained: QLearner, students: int = 400, base_seed: int = 90_000, topics: int = 5) -> dict:
    results: dict[str, dict] = {}
    for env_name, env in EVAL_ENVS.items():
        per_policy: dict[str, dict] = {}
        policy_names = ["random", "fixed_sequence", "mastery_rule", "q_learning_frozen", "q_learning_online"]
        for name in policy_names:
            gains: list[float] = []
            per_hour: list[float] = []
            final_est: list[float] = []
            online = QLearner(q=dict(trained.q), visits=dict(trained.visits)) if name == "q_learning_online" else None
            rng = random.Random(base_seed)
            policy: Policy
            if name == "random":
                policy = random_policy(rng)
            elif name == "fixed_sequence":
                policy = fixed_sequence_policy()
            elif name == "mastery_rule":
                policy = mastery_rule_policy()
            elif name == "q_learning_frozen":
                policy = qlearning_policy(trained, rng, explore=False)
            else:
                assert online is not None
                policy = qlearning_policy(online, rng, explore=True)
            for i in range(students):
                seed = base_seed + i
                outcome = run_student(policy, env, seed=seed, topics=topics, learner=online)
                gain = outcome["known_end"] - outcome["known_start"]
                gains.append(gain)
                per_hour.append(gain / (outcome["minutes"] / 60.0) if outcome["minutes"] > 0 else 0.0)
                final_est.append(outcome["estimated_mastery"])
            per_policy[name] = {
                "topics_gained": _summarize(gains),
                "topics_gained_per_study_hour": _summarize(per_hour),
                "estimated_mastery_end": _summarize(final_est),
            }
        results[env_name] = per_policy
    return results


def run_and_save(path: Path, students: int = 400, pretrain_students: int = 3000) -> dict:
    trained = pretrain(students=pretrain_students)
    results = compare_policies(trained, students=students)
    payload = {
        "disclaimer": "Simulation only. Activity effects are assumed; results do not describe real learners.",
        "pretrain_students": pretrain_students,
        "eval_students_per_policy": students,
        "results": results,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return payload
