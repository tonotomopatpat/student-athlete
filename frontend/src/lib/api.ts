export type ActivityType = "review_material" | "practice" | "quiz" | "revisit";
export type CommitmentKind = "class" | "exam" | "training" | "competition" | "travel" | "other";

export interface User {
  id: number;
  email: string;
  name: string;
  sport: string | null;
  study_window_start: number;
  study_window_end: number;
  buffer_minutes: number;
  reminder_minutes: number;
}

export interface Subject {
  id: number;
  code: string | null;
  name: string;
  description: string;
  is_builtin: boolean;
  is_sample: boolean;
  enrolled: boolean;
  topic_count: number;
}

export interface Topic {
  id: number;
  subject_id: number;
  subject_name: string;
  name: string;
  question_count: number;
  ready: boolean;
  diagnostic_done: boolean;
  mastery: number | null;
  mastered: boolean;
  material_count: number;
}

export interface SubjectDetail extends Subject {
  topics: Topic[];
}

export type ExtractionStatus = "pending" | "ok" | "failed" | "needs_review";

export interface Material {
  id: number;
  subject_id: number;
  topic_id: number | null;
  title: string;
  kind: "file" | "note" | "link";
  body: string;
  original_name: string | null;
  mime_type: string | null;
  created_at: string;
  extraction_status: ExtractionStatus;
  extraction_error: string | null;
  language: string | null;
}

export interface MaterialSection {
  id: number;
  material_id: number;
  position: number;
  title: string;
  level: number;
  page: number | null;
  word_count: number;
  topic_id: number | null;
  score: number;
  assigned_by: "auto" | "student";
}

export interface UnsortedSection extends MaterialSection {
  material_title: string;
}

export interface SyllabusPreview {
  name: string;
  code: string | null;
  topics: string[];
  warnings: string[];
}

export interface QuestionPublic {
  id: number;
  text: string;
  choices: string[];
}

export interface OwnQuestion {
  id: number;
  topic_id: number;
  text: string;
  choices: string[];
  correct_index: number;
  explanation: string;
}

export interface AnswerResult {
  question_id: number;
  correct: boolean;
  correct_index: number;
  explanation: string;
  mastery_after: number;
}

export interface SubmitResult {
  topic_id: number;
  mastery_before: number;
  mastery_after: number;
  correct_count: number;
  total: number;
  results: AnswerResult[];
  mastered: boolean;
}

export interface Commitment {
  id: number;
  title: string;
  kind: CommitmentKind;
  start_at: string;
  end_at: string;
  repeat_weekly: boolean;
  repeat_until: string | null;
}

export interface Requirement {
  id: number;
  title: string;
  due_at: string;
  subject_id: number | null;
  topic_id: number | null;
  done: boolean;
}

export interface Occurrence {
  commitment_id: number;
  title: string;
  kind: CommitmentKind;
  start_at: string;
  end_at: string;
}

export interface StudySession {
  id: number;
  recommendation_id: number;
  start_at: string | null;
  end_at: string | null;
  status: "scheduled" | "needs_reschedule";
  topic_name: string;
  subject_name: string;
  activity_type: ActivityType;
}

export interface Schedule {
  commitments: Occurrence[];
  sessions: StudySession[];
  requirements: Requirement[];
}

export interface Recommendation {
  id: number;
  topic_id: number;
  topic_name: string;
  subject_name: string;
  activity_type: ActivityType;
  reason: string;
  status: "pending" | "started" | "completed" | "skipped";
  duration_minutes: number;
  start_at: string | null;
  end_at: string | null;
  session_status: string | null;
  explored: boolean;
  created_at: string;
}

export interface ActivityStart {
  recommendation: Recommendation;
  materials: { id: number; title: string; kind: string; body: string }[];
  questions: QuestionPublic[];
}

export interface Notification {
  id: number;
  kind: string;
  title: string;
  body: string;
  link: string | null;
  scheduled_for: string;
  read_at: string | null;
}

export interface ProgressTopic {
  topic_id: number;
  topic_name: string;
  subject_name: string;
  mastery: number;
  mastered: boolean;
  responses: number;
  correct: number;
}

export interface ProgressHistory {
  topic_id: number;
  points: { at: string; mastery: number; correct: boolean }[];
}

export interface BulkResult {
  created: number;
  errors: string[];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

const NETWORK_MESSAGE = "Could not reach the server. Check your connection and try again.";

export async function request<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const finalHeaders = new Headers(headers);
  let body = rest.body;
  if (json !== undefined) {
    finalHeaders.set("Content-Type", "application/json");
    body = JSON.stringify(json);
  }
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...rest, headers: finalHeaders, body, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "network", NETWORK_MESSAGE);
  }
  if (response.status === 204) return undefined as T;
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail = (payload as { detail?: { code?: string; message?: string } | string } | null)?.detail;
    if (detail && typeof detail === "object") {
      throw new ApiError(response.status, detail.code ?? "error", detail.message ?? "Something went wrong.");
    }
    throw new ApiError(response.status, "error", typeof detail === "string" ? detail : "Something went wrong.");
  }
  return payload as T;
}

export const post = <T>(path: string, json?: unknown) => request<T>(path, { method: "POST", json: json ?? {} });
export const put = <T>(path: string, json: unknown) => request<T>(path, { method: "PUT", json });
export const patch = <T>(path: string, json: unknown) => request<T>(path, { method: "PATCH", json });
export const del = <T = void>(path: string) => request<T>(path, { method: "DELETE" });
