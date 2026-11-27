"""Route lesson sections to a subject's topics by TF-IDF cosine similarity between section text and topic names."""

import math
from collections import Counter
from dataclasses import dataclass

from app.ingest.structure import Section
from app.nlp.tokens import content_stems

MIN_SCORE = 0.12
TITLE_WEIGHT = 3
BODY_WORDS = 400


@dataclass
class Route:
    topic_id: int | None
    score: float


def _section_terms(section: Section) -> Counter[str]:
    terms: Counter[str] = Counter()
    for _ in range(TITLE_WEIGHT):
        terms.update(content_stems(section.title))
    terms.update(content_stems(" ".join(section.body_text().split()[:BODY_WORDS])))
    return terms


def _vector(terms: Counter[str], idf: dict[str, float]) -> dict[str, float]:
    vector = {term: (1 + math.log(count)) * idf.get(term, 0.0) for term, count in terms.items()}
    norm = math.sqrt(sum(value * value for value in vector.values()))
    return {term: value / norm for term, value in vector.items()} if norm else {}


def route_sections(sections: list[Section], topics: list[tuple[int, str]], fixed_topic: int | None = None) -> list[Route]:
    if fixed_topic is not None:
        return [Route(fixed_topic, 1.0) for _ in sections]
    if not topics:
        return [Route(None, 0.0) for _ in sections]
    section_terms = [_section_terms(section) for section in sections]
    topic_terms = [Counter(content_stems(name)) for _, name in topics]
    documents = section_terms + topic_terms
    frequency: Counter[str] = Counter(term for terms in documents for term in terms)
    idf = {term: math.log((1 + len(documents)) / (1 + count)) + 1 for term, count in frequency.items()}
    topic_vectors = [_vector(terms, idf) for terms in topic_terms]
    routes = []
    for terms in section_terms:
        vector = _vector(terms, idf)
        best_id, best_score = None, 0.0
        for (topic_id, _), topic_vector in zip(topics, topic_vectors):
            score = sum(weight * topic_vector.get(term, 0.0) for term, weight in vector.items())
            if score > best_score:
                best_id, best_score = topic_id, score
        routes.append(Route(best_id if best_score >= MIN_SCORE else None, round(best_score, 4)))
    return routes
