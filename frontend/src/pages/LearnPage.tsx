import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Button,
  Chip,
  Dialog,
  EmptyState,
  FormError,
  PageHeader,
  QueryBoundary,
  SectionTitle,
  TextArea,
  TextInput,
  errorMessage,
  useInvalidate,
  useToast,
} from "../components/ui";
import { post, request, type Subject, type SubjectDetail } from "../lib/api";

function SubjectCard({ subject }: { subject: Subject }) {
  const invalidate = useInvalidate();
  const toast = useToast();
  const enroll = useMutation({
    mutationFn: () => post(`/subjects/${subject.id}/enroll`),
    onSuccess: () => {
      toast(`Enrolled in ${subject.name}`);
      return invalidate("subjects", "overview", "subject");
    },
    onError: (caught) => toast(errorMessage(caught), "error"),
  });
  return (
    <li className="flex flex-col gap-3 border-2 border-ink bg-paper p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          {subject.is_sample && <Chip tone="warn">Sample</Chip>}
          {subject.is_builtin && !subject.is_sample && <Chip>Built-in</Chip>}
          {!subject.is_builtin && <Chip tone="done">Yours</Chip>}
        </div>
        <Link to={`/learn/subjects/${subject.id}`} className="block font-display text-3xl font-bold leading-tight underline-offset-4 hover:underline">
          {subject.name}
        </Link>
        <p className="num text-sm text-ink-soft">{subject.topic_count} topics</p>
        {subject.description && <p className="max-w-prose text-ink-soft">{subject.description}</p>}
      </div>
      {!subject.enrolled && (
        <Button variant="secondary" loading={enroll.isPending} onClick={() => enroll.mutate()}>
          Enroll
        </Button>
      )}
    </li>
  );
}

function NewSubjectDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const invalidate = useInvalidate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => post<SubjectDetail>("/subjects", { name, description }),
    onSuccess: async (subject) => {
      await invalidate("subjects", "overview");
      setName("");
      setDescription("");
      onClose();
      navigate(`/learn/subjects/${subject.id}`);
    },
    onError: (caught) => setError(errorMessage(caught)),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    create.mutate();
  };
  return (
    <Dialog open={open} onClose={onClose} title="New subject">
      <form onSubmit={submit} className="space-y-4">
        <TextInput label="Subject name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={160} />
        <TextArea label="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={4000} />
        <p className="text-sm text-ink-soft">Only you can see subjects you create.</p>
        <FormError message={error} />
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create subject
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function LearnPage() {
  const [creating, setCreating] = useState(false);
  const subjects = useQuery({ queryKey: ["subjects"], queryFn: () => request<Subject[]>("/subjects") });
  return (
    <div className="space-y-8">
      <PageHeader title="Learn" kicker="Subjects and topics" action={<Button onClick={() => setCreating(true)}>New subject</Button>} />
      <QueryBoundary query={subjects}>
        {(all) => {
          const mine = all.filter((s) => s.enrolled);
          const others = all.filter((s) => !s.enrolled);
          return (
            <>
              <section aria-labelledby="mine-heading">
                <SectionTitle>
                  <span id="mine-heading">My subjects</span>
                </SectionTitle>
                {mine.length === 0 ? (
                  <EmptyState title="Nothing enrolled yet">Enroll below or create a subject of your own.</EmptyState>
                ) : (
                  <ul className="space-y-3">
                    {mine.map((s) => (
                      <SubjectCard key={s.id} subject={s} />
                    ))}
                  </ul>
                )}
              </section>
              {others.length > 0 && (
                <section aria-labelledby="browse-heading">
                  <SectionTitle>
                    <span id="browse-heading">Browse subjects</span>
                  </SectionTitle>
                  <ul className="space-y-3">
                    {others.map((s) => (
                      <SubjectCard key={s.id} subject={s} />
                    ))}
                  </ul>
                </section>
              )}
            </>
          );
        }}
      </QueryBoundary>
      <NewSubjectDialog open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}
