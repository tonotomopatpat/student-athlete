import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

ACTIONS = ("review_material", "practice", "quiz", "revisit")
ACTIVITY_MINUTES = {"review_material": 15, "practice": 20, "quiz": 25, "revisit": 35}
ACTIVITY_QUESTIONS = {"review_material": 0, "practice": 5, "quiz": 8, "revisit": 4}

ALPHA = 0.15
GAMMA = 0.8
EPSILON = 0.10

# Mastery-learning prior (Guskey, 2010): low mastery -> instruction first,
# middle -> practice, high -> verification quiz. These are design assumptions,
# not learned values; they only set where learning starts.
_PRIOR = {
    0: {"review_material": 0.6, "practice": 0.2, "quiz": 0.0, "revisit": 0.8},
    1: {"review_material": 0.4, "practice": 0.6, "quiz": 0.2, "revisit": 0.6},
    2: {"review_material": 0.1, "practice": 0.6, "quiz": 0.6, "revisit": 0.2},
    3: {"review_material": 0.0, "practice": 0.3, "quiz": 0.7, "revisit": 0.0},
}


def mastery_bucket(p: float) -> int:
    if p < 0.30:
        return 0
    if p < 0.60:
        return 1
    if p < 0.85:
        return 2
    return 3


def urgency_bucket(days_to_due: float | None) -> int:
    if days_to_due is None or days_to_due > 7:
        return 0
    if days_to_due > 2:
        return 1
    return 2


def time_bucket(available_minutes: float) -> int:
    if available_minutes < 20:
        return 0
    if available_minutes < 45:
        return 1
    return 2


def recency_bucket(hours_since_activity: float | None) -> int:
    if hours_since_activity is None:
        return 0
    return 1 if hours_since_activity < 48 else 2


def make_state(mastery: float, days_to_due: float | None, available_minutes: float, hours_since: float | None) -> str:
    return (
        f"m{mastery_bucket(mastery)}-u{urgency_bucket(days_to_due)}"
        f"-t{time_bucket(available_minutes)}-r{recency_bucket(hours_since)}"
    )


def prior_q(state: str, action: str) -> float:
    return _PRIOR[int(state[1])][action]


def eligible_actions(available_minutes: float, has_material: bool, question_count: int) -> list[str]:
    """Actions whose content exists and whose duration fits the available time."""
    eligible = []
    for action in ACTIONS:
        if ACTIVITY_MINUTES[action] > available_minutes:
            continue
        if action == "review_material" and not has_material:
            continue
        if action == "practice" and question_count < 3:
            continue
        if action == "quiz" and question_count < 5:
            continue
        if action == "revisit" and not (has_material and question_count >= 3):
            continue
        eligible.append(action)
    return eligible


def compute_reward(mastery_before: float, mastery_after: float, skipped: bool) -> float:
    """Completion bonus plus scaled change in BKT mastery; penalty if skipped.

    Uses only recorded evidence: an activity that produced no new BKT evidence
    (e.g. reading) earns only the completion bonus.
    """
    if skipped:
        return -0.2
    reward = 0.1 + 4.0 * (mastery_after - mastery_before)
    return max(-1.0, min(2.0, reward))


@dataclass
class QLearner:
    q: dict[tuple[str, str], float] = field(default_factory=dict)
    visits: dict[tuple[str, str], int] = field(default_factory=dict)
    alpha: float = ALPHA
    gamma: float = GAMMA
    epsilon: float = EPSILON

    def value(self, state: str, action: str) -> float:
        return self.q.get((state, action), prior_q(state, action))

    def best_value(self, state: str, actions: Iterable[str]) -> float:
        values = [self.value(state, a) for a in actions]
        return max(values) if values else 0.0

    def select(self, state: str, eligible: list[str], rng: random.Random, explore: bool = True) -> tuple[str, bool]:
        """Epsilon-greedy over eligible actions. Returns (action, explored)."""
        if not eligible:
            raise ValueError("no eligible actions")
        if explore and rng.random() < self.epsilon:
            return rng.choice(eligible), True
        best = max(self.value(state, a) for a in eligible)
        return rng.choice([a for a in eligible if self.value(state, a) == best]), False

    def update(self, state: str, action: str, reward: float, next_state: str, next_eligible: Iterable[str]) -> float:
        current = self.value(state, action)
        target = reward + self.gamma * self.best_value(next_state, next_eligible)
        new_value = current + self.alpha * (target - current)
        self.q[(state, action)] = new_value
        self.visits[(state, action)] = self.visits.get((state, action), 0) + 1
        return new_value

    @classmethod
    def from_rows(cls, rows: Mapping[tuple[str, str], tuple[float, int]], **kwargs: float) -> "QLearner":
        learner = cls(**kwargs)
        for key, (q_value, visit_count) in rows.items():
            learner.q[key] = q_value
            learner.visits[key] = visit_count
        return learner
