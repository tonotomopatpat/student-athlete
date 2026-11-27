from dataclasses import dataclass
from collections.abc import Iterable

MASTERY_THRESHOLD = 0.95


@dataclass(frozen=True)
class BKTParams:
    """Standard four-parameter Bayesian Knowledge Tracing model.

    p_l0: P(L0) prior probability the skill is already known
    p_t:  P(T)  probability of learning the skill after a practice opportunity
    p_g:  P(G)  probability of a correct answer when the skill is not known
    p_s:  P(S)  probability of an incorrect answer when the skill is known
    """

    p_l0: float = 0.20
    p_t: float = 0.15
    p_g: float = 0.25
    p_s: float = 0.10

    def __post_init__(self) -> None:
        for name in ("p_l0", "p_t", "p_g", "p_s"):
            value = getattr(self, name)
            if not 0.0 < value < 1.0:
                raise ValueError(f"{name} must be strictly between 0 and 1, got {value}")
        if self.p_g + self.p_s >= 1.0:
            raise ValueError("p_g + p_s must be < 1 so that a correct answer is evidence of knowledge")


def update(p_known: float, correct: bool, params: BKTParams) -> float:
    """One BKT step: Bayesian evidence update followed by the learning transition."""
    if correct:
        numerator = p_known * (1.0 - params.p_s)
        denominator = numerator + (1.0 - p_known) * params.p_g
    else:
        numerator = p_known * params.p_s
        denominator = numerator + (1.0 - p_known) * (1.0 - params.p_g)
    posterior = numerator / denominator
    return posterior + (1.0 - posterior) * params.p_t


def trace(responses: Iterable[bool], params: BKTParams, p_start: float | None = None) -> list[float]:
    """Mastery estimate after each response in order."""
    p = params.p_l0 if p_start is None else p_start
    estimates: list[float] = []
    for correct in responses:
        p = update(p, correct, params)
        estimates.append(p)
    return estimates


def predict_correct(p_known: float, params: BKTParams) -> float:
    return p_known * (1.0 - params.p_s) + (1.0 - p_known) * params.p_g


def is_mastered(p_known: float) -> bool:
    return p_known >= MASTERY_THRESHOLD
