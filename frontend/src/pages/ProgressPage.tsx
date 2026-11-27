import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ACTIVITY_LABEL,
  Chip,
  EmptyState,
  Mastery,
  PageHeader,
  QueryBoundary,
  SectionTitle,
} from "../components/ui";
import { request, type ProgressHistory, type ProgressTopic, type Recommendation } from "../lib/api";
import { formatDateTime } from "../lib/time";

function MasteryChart({ topicId }: { topicId: number }) {
  const history = useQuery({
    queryKey: ["progress", "history", topicId],
    queryFn: () => request<ProgressHistory>(`/progress/topics/${topicId}`),
  });
  return (
    <QueryBoundary query={history}>
      {({ points }) => {
        if (points.length < 2) return <p className="py-2 text-ink-soft">Answer a few more questions to see a trend.</p>;
        const width = 320;
        const height = 120;
        const x = (i: number) => (i / (points.length - 1)) * width;
        const y = (m: number) => height - m * height;
        const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.mastery).toFixed(1)}`).join(" ");
        const last = points[points.length - 1];
        return (
          <figure className="py-2">
            <svg
              viewBox={`-4 -4 ${width + 8} ${height + 8}`}
              className="w-full max-w-md overflow-visible"
              role="img"
              aria-label={`Mastery over ${points.length} answers, from ${Math.round(points[0].mastery * 100)}% to ${Math.round(last.mastery * 100)}%`}
            >
              <line x1="0" x2={width} y1={y(0.95)} y2={y(0.95)} stroke="var(--color-flag)" strokeDasharray="4 4" />
              <path d={path} fill="none" stroke="var(--color-ink)" strokeWidth="3" />
              {points.map((p, i) => (
                <circle key={i} cx={x(i)} cy={y(p.mastery)} r="3.5" fill={p.correct ? "var(--color-pitch)" : "var(--color-flag)"} />
              ))}
            </svg>
            <figcaption className="text-sm text-ink-soft">Each dot is an answer (green correct, red wrong). Dashed line is the 95% mastery threshold.</figcaption>
          </figure>
        );
      }}
    </QueryBoundary>
  );
}

function Topics({ topics }: { topics: ProgressTopic[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const mastered = topics.filter((t) => t.mastered).length;
  return (
    <>
      <p className="font-display text-2xl">
        <span className="num text-4xl font-bold">{mastered}</span> of <span className="num">{topics.length}</span> topics mastered
      </p>
      <ul className="divide-y divide-line border-y-2 border-ink">
        {topics.map((t) => {
          const expanded = open === t.topic_id;
          return (
            <li key={t.topic_id} className="py-3">
              <button
                type="button"
                className="block min-h-11 w-full space-y-2 text-left"
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : t.topic_id)}
              >
                <span className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-display text-2xl font-bold">{t.topic_name}</span>
                  {t.mastered && <Chip tone="done">Mastered</Chip>}
                </span>
                <span className="block text-sm text-ink-soft">{t.subject_name}</span>
                <Mastery value={t.mastery} label={`${t.topic_name} mastery`} />
                <span className="num block text-sm text-ink-soft">
                  {t.correct} of {t.responses} answers correct · {expanded ? "Hide trend" : "Show trend"}
                </span>
              </button>
              {expanded && <MasteryChart topicId={t.topic_id} />}
            </li>
          );
        })}
      </ul>
    </>
  );
}

const STATUS_TONE = { completed: "done", skipped: "warn", started: "go", pending: "plain" } as const;

function History() {
  const history = useQuery({ queryKey: ["recommendation", "history"], queryFn: () => request<Recommendation[]>("/recommendations?limit=10") });
  return (
    <QueryBoundary query={history}>
      {(items) =>
        items.length === 0 ? null : (
          <section aria-labelledby="history-heading">
            <SectionTitle>
              <span id="history-heading">Recent activities</span>
            </SectionTitle>
            <ul className="divide-y divide-line border-y border-line">
              {items.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                  <div>
                    <p className="font-semibold">
                      {ACTIVITY_LABEL[r.activity_type]}: {r.topic_name}
                    </p>
                    <p className="text-sm text-ink-soft">{formatDateTime(r.created_at)}</p>
                  </div>
                  <Chip tone={STATUS_TONE[r.status]}>{r.status}</Chip>
                </li>
              ))}
            </ul>
          </section>
        )
      }
    </QueryBoundary>
  );
}

export function ProgressPage() {
  const progress = useQuery({ queryKey: ["progress"], queryFn: () => request<ProgressTopic[]>("/progress") });
  return (
    <div className="space-y-8">
      <PageHeader title="Progress" kicker="What you know" />
      <QueryBoundary query={progress}>
        {(topics) =>
          topics.length === 0 ? (
            <EmptyState title="No progress yet" action={<Link to="/today" className="font-semibold underline underline-offset-4">Go to Today</Link>}>
              Take a starting quiz on a topic and your mastery estimate shows up here.
            </EmptyState>
          ) : (
            <Topics topics={topics} />
          )
        }
      </QueryBoundary>
      <History />
    </div>
  );
}
