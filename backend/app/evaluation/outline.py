"""Topic-extraction evaluation: proposed syllabus topics against hand-marked outlines (data/gold/outlines/<doc_id>.txt)."""

from dataclasses import asdict, dataclass
from pathlib import Path

from app.evaluation import gold
from app.ingest.extract import extract_document
from app.ingest.syllabus import propose_topics
from app.nlp.tokens import content_stems

OUTLINES_DIR = gold.GOLD_DIR / "outlines"
MATCH_THRESHOLD = 0.5


@dataclass
class OutlineScore:
    doc_id: str
    proposed: int
    expected: int
    matched: int

    @property
    def precision(self) -> float:
        return self.matched / self.proposed if self.proposed else 0.0

    @property
    def recall(self) -> float:
        return self.matched / self.expected if self.expected else 0.0


def similarity(left: str, right: str) -> float:
    a, b = set(content_stems(left)), set(content_stems(right))
    if not a or not b:
        return 1.0 if left.strip().lower() == right.strip().lower() else 0.0
    return len(a & b) / len(a | b)


def match_count(proposed: list[str], expected: list[str], threshold: float = MATCH_THRESHOLD) -> int:
    """Greedy one-to-one matching, best pairs first."""
    pairs = sorted(
        ((similarity(p, e), i, j) for i, p in enumerate(proposed) for j, e in enumerate(expected)), reverse=True
    )
    used_p, used_e, matched = set(), set(), 0
    for score, i, j in pairs:
        if score < threshold:
            break
        if i not in used_p and j not in used_e:
            used_p.add(i)
            used_e.add(j)
            matched += 1
    return matched


def read_outline(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate(rows: list[dict[str, str]], split: str) -> dict:
    scores: list[OutlineScore] = []
    skipped: list[str] = []
    for row in rows:
        if row["kind"] != "syllabus" or row["split"] != split:
            continue
        outline_path = OUTLINES_DIR / f"{row['doc_id']}.txt"
        if not outline_path.is_file():
            skipped.append(row["doc_id"])
            continue
        proposal = propose_topics(extract_document(gold.FILES_DIR / row["path"], row["format"]))
        expected = read_outline(outline_path)
        scores.append(OutlineScore(row["doc_id"], len(proposal.topics), len(expected),
                                   match_count(proposal.topics, expected)))
    matched = sum(s.matched for s in scores)
    proposed = sum(s.proposed for s in scores)
    expected = sum(s.expected for s in scores)
    precision = matched / proposed if proposed else 0.0
    recall = matched / expected if expected else 0.0
    return {
        "split": split,
        "documents": len(scores),
        "skipped_without_outline": skipped,
        "micro_precision": round(precision, 4),
        "micro_recall": round(recall, 4),
        "micro_f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
        "per_document": [asdict(s) | {"precision": round(s.precision, 4), "recall": round(s.recall, 4)} for s in scores],
    }
