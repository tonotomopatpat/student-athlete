import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import type { Material } from "../lib/api";
import { del, post, request } from "../lib/api";
import {
  Button,
  Chip,
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
import { MaterialStatus } from "./MaterialStatus";

interface Props {
  subjectId: number;
  topicId: number;
}

function NoteDialog({ subjectId, topicId, open, onClose }: Props & { open: boolean; onClose: () => void }) {
  const invalidate = useInvalidate();
  const toast = useToast();
  const [kind, setKind] = useState<"note" | "link">("note");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => post<Material>("/materials/note", { subject_id: subjectId, topic_id: topicId, title, kind, body }),
    onSuccess: async () => {
      setTitle("");
      setBody("");
      toast("Material saved");
      await invalidate("materials", "topic", "subject", "overview");
      onClose();
    },
    onError: (caught) => setError(errorMessage(caught)),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    save.mutate();
  };
  return (
    <Dialog open={open} onClose={onClose} title="Add a note or link">
      <form onSubmit={submit} className="space-y-4">
        <SelectInput label="Type" value={kind} onChange={(e) => setKind(e.target.value as "note" | "link")}>
          <option value="note">Note (text)</option>
          <option value="link">Link</option>
        </SelectInput>
        <TextInput label="Title" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={160} />
        {kind === "note" ? (
          <TextArea label="Note" value={body} onChange={(e) => setBody(e.target.value)} required maxLength={20000} />
        ) : (
          <TextInput label="Address" type="url" placeholder="https://" value={body} onChange={(e) => setBody(e.target.value)} required />
        )}
        <FormError message={error} />
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            Save
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function MaterialRow({ material }: { material: Material }) {
  const invalidate = useInvalidate();
  const toast = useToast();
  const remove = useMutation({
    mutationFn: () => del(`/materials/${material.id}`),
    onSuccess: () => invalidate("materials", "topic", "subject", "overview"),
    onError: (caught) => toast(errorMessage(caught), "error"),
  });
  const confirmRemove = () => {
    if (window.confirm(`Delete "${material.title}"?`)) remove.mutate();
  };
  return (
    <li className="space-y-2 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap gap-2">
            <Chip>{material.kind}</Chip>
            <MaterialStatus material={material} />
          </div>
          <p className="break-words font-display text-xl font-bold">{material.title}</p>
          {material.kind === "file" && (
            <a className="font-semibold underline underline-offset-4" href={`/api/materials/${material.id}/file`} target="_blank" rel="noopener noreferrer">
              Open {material.original_name}
            </a>
          )}
          {material.kind === "link" && (
            <a className="break-all font-semibold underline underline-offset-4" href={material.body} target="_blank" rel="noopener noreferrer">
              {material.body}
            </a>
          )}
        </div>
        <Button variant="ghost" loading={remove.isPending} onClick={confirmRemove} aria-label={`Delete ${material.title}`}>
          Delete
        </Button>
      </div>
      {material.kind === "note" && (
        <details>
          <summary className="min-h-11 cursor-pointer py-2 font-semibold">Read note</summary>
          <p className="max-w-prose whitespace-pre-wrap">{material.body}</p>
        </details>
      )}
    </li>
  );
}

export function TopicMaterials({ subjectId, topicId }: Props) {
  const invalidate = useInvalidate();
  const toast = useToast();
  const fileInput = useRef<HTMLInputElement>(null);
  const [adding, setAdding] = useState(false);
  const materials = useQuery({
    queryKey: ["materials", topicId],
    queryFn: () => request<Material[]>(`/subjects/${subjectId}/materials?topic_id=${topicId}`),
  });
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("subject_id", String(subjectId));
      form.append("topic_id", String(topicId));
      form.append("file", file);
      return request<Material>("/materials/upload", { method: "POST", body: form });
    },
    onSuccess: async () => {
      toast("File uploaded");
      await invalidate("materials", "topic", "subject", "overview");
    },
    onError: (caught) => toast(errorMessage(caught), "error"),
  });
  return (
    <section aria-labelledby="materials-heading">
      <SectionTitle
        action={
          <div className="flex gap-2">
            <Button variant="secondary" loading={upload.isPending} onClick={() => fileInput.current?.click()}>
              Upload file
            </Button>
            <Button variant="secondary" onClick={() => setAdding(true)}>
              Note or link
            </Button>
          </div>
        }
      >
        <span id="materials-heading">Materials</span>
      </SectionTitle>
      <input
        ref={fileInput}
        type="file"
        className="sr-only"
        tabIndex={-1}
        aria-label="Choose a file to upload"
        accept=".pdf,.docx,.pptx,.txt,.md,.png,.jpg,.jpeg"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) upload.mutate(file);
        }}
      />
      <p className="mb-3 text-sm text-ink-soft">
        PDF, DOCX, PPTX, TXT, MD, PNG or JPG up to 15 MB. The app reads the text of documents and notes; photos and scans are kept but not read yet. Only you can see them.
      </p>
      <QueryBoundary query={materials}>
        {(items) =>
          items.length === 0 ? (
            <EmptyState title="No materials yet">Add your lecture files or notes so they show up when a review is planned.</EmptyState>
          ) : (
            <ul className="divide-y divide-line border-y border-line">
              {items.map((material) => (
                <MaterialRow key={material.id} material={material} />
              ))}
            </ul>
          )
        }
      </QueryBoundary>
      <NoteDialog subjectId={subjectId} topicId={topicId} open={adding} onClose={() => setAdding(false)} />
    </section>
  );
}
