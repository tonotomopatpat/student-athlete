import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Button,
  Chip,
  Dialog,
  EmptyState,
  FormError,
  Mastery,
  PageHeader,
  QueryBoundary,
  SectionTitle,
  TextInput,
  errorMessage,
  useInvalidate,
  useToast,
} from "../components/ui";
import { del, post, request, type SubjectDetail, type Topic } from "../lib/api";

function TopicStatus({ topic }: { topic: Topic }) {
  if (topic.mastered) return <Chip tone="done">Mastered</Chip>;
  if (!topic.ready) return <Chip tone="warn">Needs {Math.max(0, 5 - topic.question_count)} more questions</Chip>;
  if (!topic.diagnostic_done) return <Chip tone="go">Starting quiz ready</Chip>;
  return null;
}

function AddTopic({ subjectId }: { subjectId: number }) {
  const invalidate = useInvalidate();
  const toast = useToast();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const add = useMutation({
    mutationFn: () => post<Topic>(`/subjects/${subjectId}/topics`, { name }),
    onSuccess: async () => {
      setName("");
      toast("Topic added");
      await invalidate("subject", "overview", "subjects");
    },
    onError: (caught) => setError(errorMessage(caught)),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    add.mutate();
  };
  return (
    <form onSubmit={submit} className="mt-4 space-y-3 border-2 border-ink bg-paper-2 p-4">
      <TextInput label="Add a topic" value={name} onChange={(e) => setName(e.target.value)} required maxLength={160} />
      <FormError message={error} />
      <Button type="submit" loading={add.isPending}>
        Add topic
      </Button>
    </form>
  );
}

export function SubjectPage() {
  const { subjectId } = useParams();
  const navigate = useNavigate();
  const invalidate = useInvalidate();
  const toast = useToast();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const subject = useQuery({
    queryKey: ["subject", subjectId],
    queryFn: () => request<SubjectDetail>(`/subjects/${subjectId}`),
  });
  const refresh = () => invalidate("subject", "subjects", "overview", "recommendation");
  const toggleEnroll = useMutation({
    mutationFn: (enrolled: boolean) => (enrolled ? del(`/subjects/${subjectId}/enroll`) : post(`/subjects/${subjectId}/enroll`)),
    onSuccess: refresh,
    onError: (caught) => toast(errorMessage(caught), "error"),
  });
  const remove = useMutation({
    mutationFn: () => del(`/subjects/${subjectId}`),
    onSuccess: async () => {
      await refresh();
      toast("Subject deleted");
      navigate("/learn", { replace: true });
    },
    onError: (caught) => {
      setConfirmDelete(false);
      toast(errorMessage(caught), "error");
    },
  });

  return (
    <QueryBoundary query={subject}>
      {(data) => {
        const own = !data.is_builtin;
        return (
          <div className="space-y-6">
            <Link to="/learn" className="inline-block min-h-11 py-2 font-semibold underline underline-offset-4">
              ← All subjects
            </Link>
            <PageHeader
              title={data.name}
              kicker={data.is_sample ? "Sample subject" : own ? "Your subject" : "Built-in subject"}
              action={
                <div className="flex gap-2">
                  {!own && (
                    <Button
                      variant={data.enrolled ? "secondary" : "primary"}
                      loading={toggleEnroll.isPending}
                      onClick={() => toggleEnroll.mutate(data.enrolled)}
                    >
                      {data.enrolled ? "Leave" : "Enroll"}
                    </Button>
                  )}
                  {own && (
                    <Button variant="danger" onClick={() => setConfirmDelete(true)}>
                      Delete
                    </Button>
                  )}
                </div>
              }
            />
            {data.description && <p className="max-w-prose text-lg">{data.description}</p>}
            {data.is_builtin && (
              <p className="max-w-prose border-l-4 border-whistle bg-paper-2 px-3 py-2 text-sm">
                {data.is_sample ? "Sample content for trying the app. " : ""}
                Add your own questions inside a topic. Your mastery estimate depends on the answers you mark as correct, so double-check them.
              </p>
            )}
            <section aria-labelledby="topics-heading">
              <SectionTitle>
                <span id="topics-heading">Topics</span>
              </SectionTitle>
              {data.topics.length === 0 ? (
                <EmptyState title="No topics yet">{own ? "Add your first topic below." : "This subject has no topics."}</EmptyState>
              ) : (
                <ul className="divide-y divide-line border-y-2 border-ink">
                  {data.topics.map((topic) => (
                    <li key={topic.id}>
                      <Link to={`/learn/topics/${topic.id}`} className="block space-y-2 px-1 py-4 hover:bg-paper-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-display text-2xl font-bold">{topic.name}</span>
                          <TopicStatus topic={topic} />
                        </div>
                        <Mastery value={topic.mastery} label={`${topic.name} mastery`} />
                        <p className="num text-sm text-ink-soft">
                          {topic.question_count} questions · {topic.material_count} materials
                        </p>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              {own && <AddTopic subjectId={data.id} />}
            </section>
            <Dialog open={confirmDelete} onClose={() => setConfirmDelete(false)} title="Delete this subject?">
              <p>This removes its topics, questions, materials and your progress in it. It cannot be undone.</p>
              <div className="flex justify-end gap-3">
                <Button variant="secondary" onClick={() => setConfirmDelete(false)}>
                  Keep it
                </Button>
                <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
                  Delete subject
                </Button>
              </div>
            </Dialog>
          </div>
        );
      }}
    </QueryBoundary>
  );
}
