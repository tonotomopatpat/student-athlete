import csv
import io
import re
from collections.abc import Mapping

from pydantic import ValidationError

from app.schemas import QuestionIn

MAX_QUESTIONS_PER_IMPORT = 300
CHOICE_LETTERS = "ABCDEF"
_CHOICE_LINE = re.compile(r"^\s*\(?([A-Fa-f])[\).:\-]\s*(.+?)\s*$")
_ANSWER_LINE = re.compile(r"^\s*(?:answer|ans|correct)\s*[:=\-]\s*\(?([A-Fa-f])\)?\s*$", re.IGNORECASE)
_EXPLANATION_LINE = re.compile(r"^\s*(?:explanation|why)\s*[:=\-]\s*(.*)$", re.IGNORECASE)


def _validation_message(error: ValidationError) -> str:
    first = error.errors()[0]
    return str(first.get("msg", "Invalid question")).removeprefix("Value error, ")


def _build(text: str, choices: list[str], letter: str, explanation: str) -> QuestionIn:
    index = CHOICE_LETTERS.find(letter.strip().upper()[:1]) if letter.strip() else -1
    if index < 0:
        raise ValueError("Answer must be a letter such as A, B, C or D.")
    return QuestionIn(text=text, choices=choices, correct_index=index, explanation=explanation)


def parse_bulk_text(raw: str) -> tuple[list[QuestionIn], list[str]]:
    """Parse blank-line separated question blocks.

    Block format: question line(s), choice lines (A) ... B) ...), `Answer: B`,
    optional `Explanation: ...`.
    """
    questions: list[QuestionIn] = []
    errors: list[str] = []
    blocks = [b for b in re.split(r"\n\s*\n", raw.replace("\r\n", "\n").strip()) if b.strip()]
    if len(blocks) > MAX_QUESTIONS_PER_IMPORT:
        return [], [f"Too many questions at once (max {MAX_QUESTIONS_PER_IMPORT})."]
    for number, block in enumerate(blocks, start=1):
        text_lines: list[str] = []
        choices: list[str] = []
        answer = ""
        explanation = ""
        for line in block.split("\n"):
            if match := _ANSWER_LINE.match(line):
                answer = match.group(1)
            elif match := _EXPLANATION_LINE.match(line):
                explanation = match.group(1).strip()
            elif match := _CHOICE_LINE.match(line):
                if CHOICE_LETTERS.index(match.group(1).upper()) != len(choices):
                    errors.append(f"Question {number}: choices must be in order A, B, C, D.")
                    break
                choices.append(match.group(2))
            elif not choices:
                text_lines.append(line.strip())
        else:
            try:
                questions.append(_build(" ".join(text_lines).strip(), choices, answer, explanation))
            except ValidationError as error:
                errors.append(f"Question {number}: {_validation_message(error)}")
            except ValueError as error:
                errors.append(f"Question {number}: {error}")
    return questions, errors


def question_from_row(row: Mapping[str, str]) -> QuestionIn:
    normalized = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
    choices = [normalized.get(f"choice_{letter.lower()}", "") for letter in CHOICE_LETTERS]
    choices = [c for c in choices if c]
    return _build(
        normalized.get("question", ""),
        choices,
        normalized.get("correct", normalized.get("answer", "")),
        normalized.get("explanation", ""),
    )


def parse_csv(raw: bytes) -> tuple[list[QuestionIn], list[str]]:
    questions: list[QuestionIn] = []
    errors: list[str] = []
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["The CSV file must be UTF-8 encoded."]
    reader = csv.DictReader(io.StringIO(text))
    required = {"question", "choice_a", "choice_b", "correct"}
    headers = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
    if not required <= headers:
        return [], [f"CSV must have columns: question, choice_a, choice_b, ..., correct. Missing: {', '.join(sorted(required - headers))}."]
    for number, row in enumerate(reader, start=2):
        if number - 1 > MAX_QUESTIONS_PER_IMPORT:
            return [], [f"Too many questions at once (max {MAX_QUESTIONS_PER_IMPORT})."]
        try:
            questions.append(question_from_row(row))
        except ValidationError as error:
            errors.append(f"Row {number}: {_validation_message(error)}")
        except ValueError as error:
            errors.append(f"Row {number}: {error}")
    return questions, errors
