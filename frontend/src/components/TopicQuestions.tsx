import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { del, post, request, type BulkResult, type OwnQuestion } from "../lib/api";
import {
  Button,
  Dialog,
  EmptyState,
  FormError,
  QueryBoundary,
  SectionTitle,
  SelectInput,
  TextArea,
  TextInput,
  errorMessage,
  useInvalidate,
  useToast,
} from "./ui";

const LETTERS = "ABCDEF";
const BULK_EXAMPLE = `What is 2 + 2?
A) 3
B) 4
C) 5
Answer: B
Explanation: Basic addition.

Which is a prime number?
A) 9
B) 15
C) 7
Answer: C`;

type Method = "single" | "paste" | "csv";

function useAfterSave() {
  const invalidate = useInvalidate();
  const toast = useToast();
  return async (result: BulkResult) => {
    await invalidate("my-questions", "topic", "subject", "overview");
    toast(`${result.created} question${result.created === 1 ? "" : "s"} added`);
    return result;
  };
}

function SingleForm({ topicId, onDone }: { topicId: number; onDone: () => void }) {
  const afterSave = useAfterSave();
  const [text, setText] = useState("");
  const [choices, setChoices] = useState(["", "", "", ""]);
  const [correct, setCorrect] = useState(0);
  const [explanation, setExplanation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () =>
      post<BulkResult>(`/topics/${topicId}/questions`, {
        text,
        choices: choices.filter((c) => c.trim()),
        correct_index: choices.slice(0, correct).filter((c) => c.trim()).length,
        explanation,
      }),
    onSuccess: async (result) => {
      await afterSave(result);
      setText("");
      setChoices(["", "", "", ""]);
      setCorrect(0);
      setExplanation("");
      onDone();
    },
    onError: (caught) => setError(errorMessage(caught)),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!choices[correct]?.trim()) {
      setError("Mark one of the filled-in choices as the correct answer.");
      return;
    }
    save.mutate();
  };
  return (
    <form onSubmit={submit} className="space-y-4">
      <TextArea label="Question" value={text} onChange={(e) => setText(e.target.value)} required maxLength={1000} />
      <fieldset className="space-y-2">
        <legend className="label mb-1">Choices (at least 2). Select the correct one.</legend>
        {choices.map((choice, index) => (
          <div key={index} className="flex items-center gap-2">
            <input
              type="radio"
              name="correct"
              className="size-5 shrink-0 accent-ink"
              checked={correct === index}
              onChange={() => setCorrect(index)}
              aria-label={`Choice ${LETTERS[index]} is correct`}
            />
            <span className="font-display text-xl font-bold">{LETTERS[index]}</span>
            <input
              aria-label={`Choice ${LETTERS[index]}`}
              className="min-h-11 w-full border-2 border-ink bg-paper px-3"
              value={choice}
              maxLength={300}
              onChange={(e) => setChoices(choices.map((c, i) => (i === index ? e.target.value : c)))}
            />
          </div>
        ))}
      </fieldset>
      <TextInput label="Explanation (optional)" value={explanation} onChange={(e) => setExplanation(e.target.value)} maxLength={1000} />
      <FormError message={error} />
      <Button type="submit" loading={save.isPending}>
        Add question
      </Button>
    </form>
  );
}

function ImportResult({ result }: { result: BulkResult | null }) {
  if (!result || result.errors.length === 0) return null;
  return (
    <div role="status" className="border-l-4 border-whistle bg-paper-2 px-3 py-2 text-sm">
      <p className="font-semibold">{result.errors.length} skipped:</p>
      <ul className="list-disc pl-5">
        {result.errors.slice(0, 8).map((message) => (
          <li key={message}>{message}</li>
        ))}
      </ul>
    </div>
  );
}

function PasteForm({ topicId, onDone }: { topicId: number; onDone: () => void }) {
  const afterSave = useAfterSave();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BulkResult | null>(null);
  const save = useMutation({
    mutationFn: () => post<BulkResult>(`/topics/${topicId}/questions/bulk`, { text }),
    onSuccess: async (outcome) => {
      await afterSave(outcome);
      setResult(outcome);
      if (outcome.errors.length === 0) {
        setText("");
        onDone();
      }
    },
    onError: (caught) => setError(errorMessage(caught)),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setResult(null);
    save.mutate();
  };
  return (
    <form onSubmit={submit} className="space-y-4">
      <TextArea
        label="Paste questions"
        hint="Separate questions with a blank line. Choices start with A) B) C)… and end with an Answer: line."
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={BULK_EXAMPLE}
        className="min-h-56 font-mono text-sm"
        required
      />
      <FormError message={error} />
      <ImportResult result={result} />
      <Button type="submit" loading={save.isPending}>
        Add questions
      </Button>
    </form>
  );
}

function CsvForm({ topicId, onDone }: { topicId: number; onDone: () => void }) {
  const afterSave = useAfterSave();
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BulkResult | null>(null);
  const save = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return request<BulkResult>(`/topics/${topicId}/questions/csv`, { method: "POST", body: form });
    },
    onSuccess: async (outcome) => {
      await afterSave(outcome);
      setResult(outcome);
      if (outcome.errors.length === 0) onDone();
    },
    onError: (caught) => setError(errorMessage(caught)),
  });
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-soft">
        UTF-8 CSV with columns <code>question, choice_a, choice_b, choice_c, choice_d, correct, explanation</code>. <code>correct</code> is a letter.
      </p>
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv"
        aria-label="Choose a CSV file"
        className="block w-full"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          setError(null);
          setResult(null);
          if (file) save.mutate(file);
        }}
      />
      {save.isPending && <p role="status">Importing…</p>}
      <FormError message={error} />
      <ImportResult result={result} />
    </div>
  );
}

function AddDialog({ topicId, open, onClose }: { topicId: number; open: boolean; onClose: () => void }) {
  const [method, setMethod] = useState<Method>("single");
  return (
    <Dialog open={open} onClose={onClose} title="Add questions">
      <div className="space-y-4">
        <SelectInput label="How" value={method} onChange={(e) => setMethod(e.target.value as Method)}>
          <option value="single">One at a time</option>
          <option value="paste">Paste several</option>
          <option value="csv">Upload CSV</option>
        </SelectInput>
        <p className="border-l-4 border-whistle bg-paper-2 px-3 py-2 text-sm">
          Your mastery score is only as good as the answer keys you write. Double-check each correct answer.
        </p>
        {method === "single" && <SingleForm topicId={topicId} onDone={onClose} />}
        {method === "paste" && <PasteForm topicId={topicId} onDone={onClose} />}
        {method === "csv" && <CsvForm topicId={topicId} onDone={onClose} />}
      </div>
    </Dialog>
  );
}

export function TopicQuestions({ topicId, questionCount }: { topicId: number; questionCount: number }) {
  const invalidate = useInvalidate();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const questions = useQuery({
    queryKey: ["my-questions", topicId],
    queryFn: () => request<OwnQuestion[]>(`/topics/${topicId}/my-questions`),
  });
  const remove = useMutation({
    mutationFn: (id: number) => del(`/questions/${id}`),
    onSuccess: () => invalidate("my-questions", "topic", "subject", "overview"),
    onError: (caught) => toast(errorMessage(caught), "error"),
  });
  return (
    <section aria-labelledby="questions-heading">
      <SectionTitle action={<Button onClick={() => setAdding(true)}>Add questions</Button>}>
        <span id="questions-heading">My questions</span>
      </SectionTitle>
      <p className="mb-3 text-sm text-ink-soft">
        <span className="num">{questionCount}</span> available in total (including built-in ones). Each topic needs at least 5 before it can be quizzed.
      </p>
      <QueryBoundary query={questions}>
        {(items) =>
          items.length === 0 ? (
            <EmptyState title="You have not written any questions here">Write multiple-choice questions from your own lectures.</EmptyState>
          ) : (
            <ol className="divide-y divide-line border-y border-line">
              {items.map((question) => (
                <li key={question.id} className="flex items-start justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="font-semibold">{question.text}</p>
                    <p className="text-sm text-ink-soft">
                      Answer: {LETTERS[question.correct_index]}. {question.choices[question.correct_index]}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    aria-label={`Delete question: ${question.text}`}
                    loading={remove.isPending && remove.variables === question.id}
                    onClick={() => {
                      if (window.confirm("Delete this question?")) remove.mutate(question.id);
                    }}
                  >
                    Delete
                  </Button>
                </li>
              ))}
            </ol>
          )
        }
      </QueryBoundary>
      <AddDialog topicId={topicId} open={adding} onClose={() => setAdding(false)} />
    </section>
  );
}
