import { buildAgenda } from "./agenda";
import type { Schedule } from "./api";

const schedule: Schedule = {
  commitments: [
    { commitment_id: 1, title: "Training", kind: "training", start_at: "2026-03-02T16:00:00", end_at: "2026-03-02T18:00:00" },
    { commitment_id: 2, title: "Class", kind: "class", start_at: "2026-03-02T09:00:00", end_at: "2026-03-02T10:00:00" },
  ],
  sessions: [
    {
      id: 5,
      recommendation_id: 9,
      start_at: "2026-03-03T07:00:00",
      end_at: "2026-03-03T07:20:00",
      status: "scheduled",
      topic_name: "Sets",
      subject_name: "Math",
      activity_type: "practice",
    },
    {
      id: 6,
      recommendation_id: 10,
      start_at: null,
      end_at: null,
      status: "needs_reschedule",
      topic_name: "Sets",
      subject_name: "Math",
      activity_type: "quiz",
    },
  ],
  requirements: [
    { id: 1, title: "Quiz 1", due_at: "2026-03-03T10:00:00", subject_id: null, topic_id: null, done: false },
    { id: 2, title: "Done essay", due_at: "2026-03-03T12:00:00", subject_id: null, topic_id: null, done: true },
  ],
};

describe("buildAgenda", () => {
  const agenda = buildAgenda(schedule, new Date(2026, 2, 2), 3);

  it("creates one bucket per day", () => {
    expect(agenda.map((d) => d.key)).toEqual(["2026-03-02", "2026-03-03", "2026-03-04"]);
  });

  it("sorts items by start time within a day", () => {
    expect(agenda[0].items.map((i) => i.title)).toEqual(["Class", "Training"]);
  });

  it("includes scheduled sessions and open deadlines but skips unplaced sessions and done items", () => {
    expect(agenda[1].items.map((i) => i.title)).toEqual(["Practice: Sets", "Quiz 1"]);
    expect(agenda[1].items[0].link).toBe("/activity/9");
  });
});
