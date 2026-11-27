import type { CommitmentKind, Schedule } from "./api";
import { addDays, dayKey, toDateInput } from "./time";

export type AgendaKind = "commitment" | "session" | "due";

export interface AgendaItem {
  key: string;
  kind: AgendaKind;
  start: string;
  end: string | null;
  title: string;
  detail: string;
  commitmentKind?: CommitmentKind;
  link?: string;
}

export interface AgendaDay {
  key: string;
  date: Date;
  items: AgendaItem[];
}

const ACTIVITY_NAMES: Record<string, string> = {
  review_material: "Review",
  practice: "Practice",
  quiz: "Quiz",
  revisit: "Revisit",
};

export function buildAgenda(schedule: Schedule, from: Date, days: number): AgendaDay[] {
  const buckets = new Map<string, AgendaItem[]>();
  const result: AgendaDay[] = [];
  for (let i = 0; i < days; i += 1) {
    const date = addDays(from, i);
    const key = toDateInput(date);
    buckets.set(key, []);
    result.push({ key, date, items: buckets.get(key)! });
  }
  const add = (item: AgendaItem) => buckets.get(dayKey(item.start))?.push(item);

  for (const c of schedule.commitments) {
    add({
      key: `c-${c.commitment_id}-${c.start_at}`,
      kind: "commitment",
      start: c.start_at,
      end: c.end_at,
      title: c.title,
      detail: c.kind,
      commitmentKind: c.kind,
    });
  }
  for (const s of schedule.sessions) {
    if (!s.start_at) continue;
    add({
      key: `s-${s.id}`,
      kind: "session",
      start: s.start_at,
      end: s.end_at,
      title: `${ACTIVITY_NAMES[s.activity_type] ?? "Study"}: ${s.topic_name}`,
      detail: s.subject_name,
      link: `/activity/${s.recommendation_id}`,
    });
  }
  for (const r of schedule.requirements) {
    if (r.done) continue;
    add({ key: `r-${r.id}`, kind: "due", start: r.due_at, end: null, title: r.title, detail: "Due" });
  }
  for (const day of result) day.items.sort((a, b) => a.start.localeCompare(b.start));
  return result;
}
