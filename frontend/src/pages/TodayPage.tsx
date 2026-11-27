import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Timeline } from "../components/Timeline";
import {
  ACTIVITY_HELP,
  ACTIVITY_LABEL,
  Button,
  Chip,
  EmptyState,
  FormError,
  LinkButton,
  PageHeader,
  QueryBoundary,
  SectionTitle,
  errorMessage,
  useInvalidate,
} from "../components/ui";
import { buildAgenda } from "../lib/agenda";
import { post, request, type Recommendation, type Schedule, type SubjectDetail } from "../lib/api";
import { useMe } from "../lib/auth";
import { formatDateTime, greeting, startOfDay, toNaiveIso } from "../lib/time";

function NextUp({ recommendation }: { recommendation: Recommendation | null }) {
  const invalidate = useInvalidate();
  const [error, setError] = useState<string | null>(null);
  const getNext = useMutation({
    mutationFn: () => post<Recommendation>("/recommendations/next"),
    onSuccess: () => invalidate("recommendation", "schedule"),
    onError: (caught) => setError(errorMessage(caught)),
  });
  const skip = useMutation({
    mutationFn: (id: number) => post(`/recommendations/${id}/skip`),
    onSuccess: () => invalidate("recommendation", "schedule", "progress"),
    onError: (caught) => setError(errorMessage(caught)),
  });

  if (!recommendation) {
    return (
      <div className="border-2 border-ink bg-paper-2 p-5">
        <p className="label">Next up</p>
        <h2 className="mt-1 text-4xl">Ready when you are</h2>
        <p className="mt-2 max-w-prose text-ink-soft">
          Your plan picks the topic and the activity that should help most right now, and fits it around your training and classes.
        </p>
        <div className="mt-4 space-y-3">
          <FormError message={error} />
          <Button loading={getNext.isPending} onClick={() => { setError(null); getNext.mutate(); }}>
            Get my next activity
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="border-2 border-ink bg-whistle p-5">
      <div className="flex flex-wrap items-center gap-2">
        <p className="label !text-ink">Next up</p>
        <Chip tone="go">{ACTIVITY_LABEL[recommendation.activity_type]}</Chip>
        <span className="num text-sm font-semibold">{recommendation.duration_minutes} min</span>
      </div>
      <h2 className="mt-1 text-4xl">{recommendation.topic_name}</h2>
      <p className="font-semibold">{recommendation.subject_name}</p>
      <p className="mt-2 max-w-prose">{recommendation.reason}</p>
      <p className="mt-1 text-sm">{ACTIVITY_HELP[recommendation.activity_type]}</p>
      <p className="mt-2 font-semibold" role="status">
        {recommendation.start_at
          ? `Scheduled ${formatDateTime(recommendation.start_at)}`
          : "No free slot yet. You can still start now, or re-plan after changing your schedule."}
      </p>
      <div className="mt-4 space-y-3">
        <FormError message={error} />
        <div className="flex flex-wrap gap-3">
          <LinkButton to={`/activity/${recommendation.id}`}>{recommendation.status === "started" ? "Continue" : "Start"}</LinkButton>
          <Button variant="secondary" loading={skip.isPending} onClick={() => { setError(null); skip.mutate(recommendation.id); }}>
            Not now
          </Button>
        </div>
      </div>
    </div>
  );
}

function Diagnostics({ subjects }: { subjects: SubjectDetail[] }) {
  const pending = subjects.flatMap((subject) =>
    subject.topics.filter((topic) => topic.ready && !topic.diagnostic_done).map((topic) => ({ subject, topic })),
  );
  if (pending.length === 0) return null;
  return (
    <section aria-labelledby="start-heading">
      <SectionTitle>
        <span id="start-heading">Starting quizzes</span>
      </SectionTitle>
      <p className="mb-3 max-w-prose text-ink-soft">
        A short quiz sets your starting level. A topic joins your plan once its quiz is done.
      </p>
      <ul className="divide-y divide-line border-y border-line">
        {pending.map(({ subject, topic }) => (
          <li key={topic.id} className="flex items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <p className="truncate font-display text-xl font-bold">{topic.name}</p>
              <p className="truncate text-sm text-ink-soft">{subject.name}</p>
            </div>
            <LinkButton to={`/assessment/${topic.id}/diagnostic`} variant="secondary">
              Take quiz
            </LinkButton>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function TodayPage() {
  const me = useMe();
  const now = useMemo(() => new Date(), []);
  const from = startOfDay(now);
  const overview = useQuery({ queryKey: ["overview"], queryFn: () => request<SubjectDetail[]>("/overview") });
  const current = useQuery({
    queryKey: ["recommendation", "current"],
    queryFn: () => request<Recommendation | null>("/recommendations/current"),
  });
  const schedule = useQuery({
    queryKey: ["schedule", "today", toNaiveIso(from)],
    queryFn: () => request<Schedule>(`/schedule?start=${toNaiveIso(from)}&end=${toNaiveIso(new Date(from.getTime() + 2 * 86_400_000))}`),
  });

  return (
    <div className="space-y-8">
      <PageHeader kicker={greeting(now)} title={me.data?.name.split(" ")[0] ?? "Today"} />

      <QueryBoundary query={overview}>
        {(subjects) =>
          subjects.length === 0 ? (
            <EmptyState
              title="Pick what you are studying"
              action={<LinkButton to="/learn">Choose subjects</LinkButton>}
            >
              Enroll in a built-in subject or create your own, add questions, and your plan starts from there.
            </EmptyState>
          ) : (
            <>
              <Diagnostics subjects={subjects} />
              <QueryBoundary query={current}>{(recommendation) => <NextUp recommendation={recommendation} />}</QueryBoundary>
            </>
          )
        }
      </QueryBoundary>

      <section aria-labelledby="coming-heading">
        <SectionTitle
          action={
            <Link to="/plan" className="font-semibold underline underline-offset-4">
              Full plan
            </Link>
          }
        >
          <span id="coming-heading">Coming up</span>
        </SectionTitle>
        <QueryBoundary query={schedule}>{(data) => <Timeline days={buildAgenda(data, from, 2)} />}</QueryBoundary>
      </section>
    </div>
  );
}
