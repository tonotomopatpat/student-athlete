import { useMutation } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { post, request, type SubjectDetail, type SyllabusPreview } from "../lib/api";
import { Button, Dialog, FormError, TextInput, errorMessage, useInvalidate } from "./ui";

const MAX_TOPICS = 40;

const WARNING_TEXT: Record<string, string> = {
  no_name_found: "We could not find the course title. Type it in.",
  no_topics_found: "We could not find a topic list. Add the topics yourself, or try another file.",
  few_topics: "Only a few topics were found. Check the list against your syllabus.",
  no_text_layer: "This looks like a scanned file, so little text could be read.",
};

interface DraftTopic {
  key: number;
  name: string;
}

function TopicEditor({ topics, onChange }: { topics: DraftTopic[]; onChange: (next: DraftTopic[]) => void }) {
  const nextKey = useRef(10_000);
  const move = (index: number, offset: number) => {
    const next = [...topics];
    const [item] = next.splice(index, 1);
    next.splice(index + offset, 0, item);
    onChange(next);
  };
  return (
    <div className="space-y-2">
      <p className="label">Topics, in order</p>
      <ol className="space-y-2">
        {topics.map((topic, index) => (
          <li key={topic.key} className="flex items-center gap-1">
            <span className="num w-7 shrink-0 text-right font-display text-lg text-ink-soft">{index + 1}</span>
            <input
              aria-label={`Topic ${index + 1}`}
              value={topic.name}
              maxLength={160}
              onChange={(event) => onChange(topics.map((t) => (t.key === topic.key ? { ...t, name: event.target.value } : t)))}
              className="min-h-11 min-w-0 flex-1 border-2 border-ink bg-paper px-2 py-1"
            />
            <button type="button" className="min-h-11 min-w-9 disabled:opacity-30" disabled={index === 0} onClick={() => move(index, -1)} aria-label={`Move topic ${index + 1} up`}>
              ↑
            </button>
            <button type="button" className="min-h-11 min-w-9 disabled:opacity-30" disabled={index === topics.length - 1} onClick={() => move(index, 1)} aria-label={`Move topic ${index + 1} down`}>
              ↓
            </button>
            <button type="button" className="min-h-11 min-w-9 text-flag" onClick={() => onChange(topics.filter((t) => t.key !== topic.key))} aria-label={`Remove topic ${index + 1}`}>
              ×
            </button>
          </li>
        ))}
      </ol>
      {topics.length < MAX_TOPICS && (
        <Button variant="ghost" onClick={() => onChange([...topics, { key: nextKey.current++, name: "" }])}>
          Add a topic
        </Button>
      )}
    </div>
  );
}

export function SyllabusDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const invalidate = useInvalidate();
  const fileInput = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<SyllabusPreview | null>(null);
  const [name, setName] = useState("");
  const [topics, setTopics] = useState<DraftTopic[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setPreview(null);
    setName("");
    setTopics([]);
    setError(null);
  };
  const close = () => {
    reset();
    onClose();
  };

  const read = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return request<SyllabusPreview>("/syllabus/preview", { method: "POST", body: form });
    },
    onSuccess: (result) => {
      setPreview(result);
      setName(result.name);
      setTopics(result.topics.map((topicName, index) => ({ key: index, name: topicName })));
    },
    onError: (caught) => setError(errorMessage(caught)),
  });

  const confirm = useMutation({
    mutationFn: () =>
      post<SubjectDetail>("/syllabus/confirm", { name: name.trim(), topics: topics.map((t) => t.name.trim()).filter(Boolean) }),
    onSuccess: async (subject) => {
      await invalidate("subjects", "overview");
      close();
      navigate(`/learn/subjects/${subject.id}`);
    },
    onError: (caught) => setError(errorMessage(caught)),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!topics.some((t) => t.name.trim())) {
      setError("Keep at least one topic.");
      return;
    }
    confirm.mutate();
  };

  return (
    <Dialog open={open} onClose={close} title={preview ? "Check your subject" : "Start from your syllabus"}>
      {!preview ? (
        <div className="space-y-4">
          <p>Upload your course syllabus. We will propose the subject and its topics. You can fix anything before it is saved.</p>
          <p className="text-sm text-ink-soft">PDF, DOCX, PPTX or TXT, up to 15 MB. The file itself is not kept.</p>
          <input
            ref={fileInput}
            type="file"
            className="sr-only"
            tabIndex={-1}
            aria-label="Choose your syllabus file"
            accept=".pdf,.docx,.pptx,.txt,.md"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              setError(null);
              if (file) read.mutate(file);
            }}
          />
          <FormError message={error} />
          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={close}>
              Cancel
            </Button>
            <Button loading={read.isPending} onClick={() => fileInput.current?.click()}>
              Choose syllabus
            </Button>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          {preview.warnings.map((warning) => (
            <p key={warning} className="border-l-4 border-whistle bg-paper-2 px-3 py-2 text-sm">
              {WARNING_TEXT[warning] ?? warning}
            </p>
          ))}
          <TextInput label="Subject name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={160} />
          {preview.code && <p className="num text-sm text-ink-soft">Course code found: {preview.code}</p>}
          <TopicEditor topics={topics} onChange={setTopics} />
          <FormError message={error} />
          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={reset}>
              Pick another file
            </Button>
            <Button type="submit" loading={confirm.isPending}>
              Create subject
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
