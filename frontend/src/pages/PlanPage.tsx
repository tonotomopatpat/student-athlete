import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { CommitmentDialog, KIND_OPTIONS, RequirementDialog } from "../components/PlanDialogs";
import { Timeline } from "../components/Timeline";
import {
  Button,
  Chip,
  EmptyState,
  PageHeader,
  QueryBoundary,
  SectionTitle,
  errorMessage,
  useInvalidate,
  useToast,
} from "../components/ui";
import { buildAgenda } from "../lib/agenda";
import { del, patch, post, request, type Commitment, type Requirement, type Schedule } from "../lib/api";
import { addDays, formatDateTime, formatDay, startOfDay, toNaiveIso } from "../lib/time";

const kindLabel = (kind: string) => KIND_OPTIONS.find((o) => o.value === kind)?.label ?? kind;

function Commitments() {
  const invalidate = useInvalidate();
  const toast = useToast();
  const [editing, setEditing] = useState<Commitment | null>(null);
  const [adding, setAdding] = useState(false);
  const commitments = useQuery({ queryKey: ["commitments"], queryFn: () => request<Commitment[]>("/commitments") });
  const remove = useMutation({
    mutationFn: (id: number) => del(`/commitments/${id}`),
    onSuccess: () => invalidate("schedule", "commitments", "recommendation"),
    onError: (caught) => toast(errorMessage(caught), "error"),
  });
  return (
    <section aria-labelledby="commitments-heading">
      <SectionTitle action={<Button variant="secondary" onClick={() => setAdding(true)}>Add commitment</Button>}>
        <span id="commitments-heading">Classes, training and games</span>
      </SectionTitle>
      <QueryBoundary query={commitments}>
        {(items) =>
          items.length === 0 ? (
            <EmptyState title="Nothing added yet">Add your class, training and game times so study sessions never collide with them.</EmptyState>
          ) : (
            <ul className="divide-y divide-line border-y border-line">
              {items.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                  <div className="min-w-0">
                    <p className="font-display text-xl font-bold">{c.title}</p>
                    <p className="text-sm text-ink-soft">
                      {kindLabel(c.kind)} · {c.repeat_weekly ? `Every ${formatDay(c.start_at, "short").split(",")[0]}` : formatDateTime(c.start_at)}
                      {c.repeat_weekly && c.repeat_until ? ` until ${c.repeat_until}` : ""}
                    </p>
                  </div>
                  <div className="flex gap-1">
                    <Button variant="ghost" onClick={() => setEditing(c)} aria-label={`Edit ${c.title}`}>
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      aria-label={`Delete ${c.title}`}
                      onClick={() => {
                        if (window.confirm(`Delete "${c.title}"?`)) remove.mutate(c.id);
                      }}
                    >
                      Delete
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )
        }
      </QueryBoundary>
      {adding && <CommitmentDialog open onClose={() => setAdding(false)} />}
      {editing && <CommitmentDialog key={editing.id} open initial={editing} onClose={() => setEditing(null)} />}
    </section>
  );
}

function Deadlines() {
  const invalidate = useInvalidate();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const requirements = useQuery({ queryKey: ["requirements"], queryFn: () => request<Requirement[]>("/requirements") });
  const refresh = () => invalidate("schedule", "requirements", "recommendation");
  const toggle = useMutation({
    mutationFn: (r: Requirement) => patch(`/requirements/${r.id}`, { done: !r.done }),
    onSuccess: refresh,
    onError: (caught) => toast(errorMessage(caught), "error"),
  });
  const remove = useMutation({
    mutationFn: (id: number) => del(`/requirements/${id}`),
    onSuccess: refresh,
    onError: (caught) => toast(errorMessage(caught), "error"),
  });
  return (
    <section aria-labelledby="deadlines-heading">
      <SectionTitle action={<Button variant="secondary" onClick={() => setAdding(true)}>Add deadline</Button>}>
        <span id="deadlines-heading">Deadlines</span>
      </SectionTitle>
      <QueryBoundary query={requirements}>
        {(items) =>
          items.length === 0 ? (
            <EmptyState title="No deadlines">Tasks and submissions you add show up here and in your plan.</EmptyState>
          ) : (
            <ul className="divide-y divide-line border-y border-line">
              {items.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                  <label className="flex min-h-11 min-w-0 items-center gap-3">
                    <input type="checkbox" className="size-5 accent-ink" checked={r.done} onChange={() => toggle.mutate(r)} />
                    <span className={r.done ? "text-ink-soft line-through" : "font-semibold"}>
                      {r.title} <span className="font-normal text-ink-soft">· {formatDateTime(r.due_at)}</span>
                    </span>
                  </label>
                  <Button
                    variant="ghost"
                    aria-label={`Delete ${r.title}`}
                    onClick={() => {
                      if (window.confirm(`Delete "${r.title}"?`)) remove.mutate(r.id);
                    }}
                  >
                    Delete
                  </Button>
                </li>
              ))}
            </ul>
          )
        }
      </QueryBoundary>
      {adding && <RequirementDialog open onClose={() => setAdding(false)} />}
    </section>
  );
}

export function PlanPage() {
  const invalidate = useInvalidate();
  const toast = useToast();
  const today = useMemo(() => startOfDay(new Date()), []);
  const [weekOffset, setWeekOffset] = useState(0);
  const from = addDays(today, weekOffset * 7);
  const to = addDays(from, 7);
  const schedule = useQuery({
    queryKey: ["schedule", "plan", toNaiveIso(from)],
    queryFn: () => request<Schedule>(`/schedule?start=${toNaiveIso(from)}&end=${toNaiveIso(to)}`),
  });
  const replan = useMutation({
    mutationFn: () => post<{ placed: number }>("/schedule/replan"),
    onSuccess: async (result) => {
      toast(result.placed > 0 ? `Placed ${result.placed} session${result.placed === 1 ? "" : "s"}` : "Nothing needed re-planning");
      await invalidate("schedule", "recommendation");
    },
    onError: (caught) => toast(errorMessage(caught), "error"),
  });
  const unplaced = schedule.data?.sessions.filter((s) => s.status === "needs_reschedule") ?? [];

  return (
    <div className="space-y-8">
      <PageHeader title="Plan" kicker="Your week" action={<Button variant="secondary" loading={replan.isPending} onClick={() => replan.mutate()}>Re-plan</Button>} />
      {unplaced.length > 0 && (
        <p role="status" className="border-l-4 border-flag bg-flag-soft px-3 py-2 font-semibold">
          {unplaced.length} study session{unplaced.length === 1 ? " needs" : "s need"} a new time. Press Re-plan to place {unplaced.length === 1 ? "it" : "them"}.
          {unplaced.map((s) => ` ${s.topic_name}`).join(",")}
        </p>
      )}
      <section aria-labelledby="week-heading">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 id="week-heading" className="label !text-base">
            {formatDay(from, "short")} – {formatDay(addDays(from, 6), "short")}
          </h2>
          <div className="flex gap-2">
            <Button variant="secondary" disabled={weekOffset === 0} onClick={() => setWeekOffset(weekOffset - 1)} aria-label="Previous week">
              ←
            </Button>
            <Button variant="secondary" onClick={() => setWeekOffset(weekOffset + 1)} aria-label="Next week">
              →
            </Button>
          </div>
        </div>
        <QueryBoundary query={schedule}>{(data) => <Timeline days={buildAgenda(data, from, 7)} />}</QueryBoundary>
        <p className="mt-4 flex flex-wrap items-center gap-2 text-sm text-ink-soft">
          <Chip tone="go">Study</Chip> planned sessions
          <Chip>Busy</Chip> hatched blocks are classes, training and games
          <Chip tone="warn">Due</Chip> deadlines
        </p>
      </section>
      <Commitments />
      <Deadlines />
    </div>
  );
}
