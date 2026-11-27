import { useState, type ReactNode } from "react";
import type { QuestionPublic, SubmitResult } from "../lib/api";
import { Button, FormError, Mastery, errorMessage } from "./ui";

interface Props {
  questions: QuestionPublic[];
  submit: (answers: { question_id: number; chosen_index: number }[]) => Promise<SubmitResult>;
  onFinished?: (result: SubmitResult) => void;
  doneAction: ReactNode;
}

const LETTERS = "ABCDEF";

export function QuestionRunner({ questions, submit, onFinished, doneAction }: Props) {
  const [index, setIndex] = useState(0);
  const [chosen, setChosen] = useState<Record<number, number>>({});
  const [result, setResult] = useState<SubmitResult | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (result) return <Results questions={questions} chosen={chosen} result={result} doneAction={doneAction} />;

  const question = questions[index];
  const isLast = index === questions.length - 1;
  const answeredAll = questions.every((q) => chosen[q.id] !== undefined);

  const finish = async () => {
    setPending(true);
    setError(null);
    try {
      const outcome = await submit(questions.map((q) => ({ question_id: q.id, chosen_index: chosen[q.id] })));
      setResult(outcome);
      onFinished?.(outcome);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setPending(false);
    }
  };

  return (
    <section aria-labelledby="question-heading" className="space-y-5">
      <div className="flex items-center justify-between">
        <p className="label" id="question-heading">
          Question <span className="num">{index + 1}</span> of <span className="num">{questions.length}</span>
        </p>
        <div className="flex gap-1" aria-hidden>
          {questions.map((q, i) => (
            <span
              key={q.id}
              className={`h-2 w-6 ${i === index ? "bg-ink" : chosen[q.id] !== undefined ? "bg-ink-soft" : "bg-line"}`}
            />
          ))}
        </div>
      </div>
      <fieldset className="space-y-3">
        <legend className="mb-3 font-display text-3xl font-bold leading-tight">{question.text}</legend>
        {question.choices.map((choice, choiceIndex) => {
          const selected = chosen[question.id] === choiceIndex;
          return (
            <label
              key={choiceIndex}
              className={`flex min-h-14 cursor-pointer items-center gap-3 border-2 px-4 py-3 ${
                selected ? "border-ink bg-whistle" : "border-ink bg-paper hover:bg-paper-2"
              }`}
            >
              <input
                type="radio"
                name={`q-${question.id}`}
                className="size-5 accent-ink"
                checked={selected}
                onChange={() => setChosen((current) => ({ ...current, [question.id]: choiceIndex }))}
              />
              <span className="font-display text-2xl font-bold">{LETTERS[choiceIndex]}</span>
              <span className="text-lg">{choice}</span>
            </label>
          );
        })}
      </fieldset>
      <FormError message={error} />
      <div className="flex justify-between gap-3">
        <Button variant="secondary" disabled={index === 0} onClick={() => setIndex(index - 1)}>
          Back
        </Button>
        {isLast ? (
          <Button loading={pending} disabled={!answeredAll} onClick={() => void finish()}>
            Submit answers
          </Button>
        ) : (
          <Button disabled={chosen[question.id] === undefined} onClick={() => setIndex(index + 1)}>
            Next
          </Button>
        )}
      </div>
      {isLast && !answeredAll && <p className="text-sm text-ink-soft">Answer every question to submit.</p>}
    </section>
  );
}

function Results({
  questions,
  chosen,
  result,
  doneAction,
}: {
  questions: QuestionPublic[];
  chosen: Record<number, number>;
  result: SubmitResult;
  doneAction: ReactNode;
}) {
  const byId = new Map(result.results.map((r) => [r.question_id, r]));
  const delta = Math.round((result.mastery_after - result.mastery_before) * 100);
  return (
    <section aria-labelledby="result-heading" className="space-y-6">
      <div className="border-2 border-ink bg-paper-2 p-5">
        <h2 id="result-heading" className="text-5xl">
          <span className="num">{result.correct_count}</span> of <span className="num">{result.total}</span> correct
        </h2>
        <div className="mt-4 space-y-2">
          <p className="label">Mastery estimate</p>
          <Mastery value={result.mastery_before} label="Mastery before" />
          <Mastery value={result.mastery_after} label="Mastery after" />
          <p className="font-semibold" role="status">
            {result.mastered
              ? "You have mastered this topic."
              : delta >= 0
                ? `Up ${delta} points.`
                : `Down ${Math.abs(delta)} points. Review the explanations below.`}
          </p>
        </div>
      </div>
      <ol className="space-y-4">
        {questions.map((question, i) => {
          const outcome = byId.get(question.id);
          if (!outcome) return null;
          return (
            <li key={question.id} className={`border-l-4 px-4 py-3 ${outcome.correct ? "border-pitch bg-pitch-soft" : "border-flag bg-flag-soft"}`}>
              <p className="label !text-ink">
                {i + 1}. {outcome.correct ? "Correct" : "Not quite"}
              </p>
              <p className="font-semibold">{question.text}</p>
              {!outcome.correct && (
                <p>
                  You chose: <span className="font-semibold">{question.choices[chosen[question.id]]}</span>
                </p>
              )}
              <p>
                Answer: <span className="font-semibold">{question.choices[outcome.correct_index]}</span>
              </p>
              {outcome.explanation && <p className="text-ink-soft">{outcome.explanation}</p>}
            </li>
          );
        })}
      </ol>
      <div>{doneAction}</div>
    </section>
  );
}
