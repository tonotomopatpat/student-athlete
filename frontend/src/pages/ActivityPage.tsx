import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { QuestionRunner } from "../components/QuestionRunner";
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
  errorMessage,
  useInvalidate,
} from "../components/ui";
import { post, type ActivityStart, type SubmitResult } from "../lib/api";

function Materials({ items }: { items: ActivityStart["materials"] }) {
  if (items.length === 0) {
    return <EmptyState title="No materials for this topic">You can add notes or files on the topic page. You can still answer the questions.</EmptyState>;
  }
  return (
    <ul className="divide-y divide-line border-y border-line">
      {items.map((material) => (
        <li key={material.id} className="space-y-1 py-3">
          <Chip>{material.kind}</Chip>
          <p className="font-display text-xl font-bold">{material.title}</p>
          {material.kind === "file" && (
            <a className="font-semibold underline underline-offset-4" href={`/api/materials/${material.id}/file`} target="_blank" rel="noopener noreferrer">
              Open file
            </a>
          )}
          {material.kind === "link" && (
            <a className="break-all font-semibold underline underline-offset-4" href={material.body} target="_blank" rel="noopener noreferrer">
              {material.body}
            </a>
          )}
          {material.kind === "note" && <p className="max-w-prose whitespace-pre-wrap">{material.body}</p>}
        </li>
      ))}
    </ul>
  );
}

function ReviewDone({ recommendationId }: { recommendationId: number }) {
  const navigate = useNavigate();
  const invalidate = useInvalidate();
  const [error, setError] = useState<string | null>(null);
  const complete = useMutation({
    mutationFn: () => post(`/recommendations/${recommendationId}/complete`),
    onSuccess: async () => {
      await invalidate("recommendation", "schedule", "progress", "overview", "notifications");
      navigate("/today", { replace: true });
    },
    onError: (caught) => setError(errorMessage(caught)),
  });
  return (
    <div className="space-y-3">
      <FormError message={error} />
      <Button loading={complete.isPending} onClick={() => { setError(null); complete.mutate(); }}>
        I have finished reviewing
      </Button>
    </div>
  );
}

export function ActivityPage() {
  const { recommendationId } = useParams();
  const navigate = useNavigate();
  const invalidate = useInvalidate();
  const [skipError, setSkipError] = useState<string | null>(null);
  const [finished, setFinished] = useState(false);
  const activity = useQuery({
    queryKey: ["activity", recommendationId],
    queryFn: () => post<ActivityStart>(`/recommendations/${recommendationId}/start`),
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: false,
  });
  const skip = useMutation({
    mutationFn: () => post(`/recommendations/${recommendationId}/skip`),
    onSuccess: async () => {
      await invalidate("recommendation", "schedule", "progress");
      navigate("/today", { replace: true });
    },
    onError: (caught) => setSkipError(errorMessage(caught)),
  });
  const refresh = () => {
    setFinished(true);
    void invalidate("recommendation", "schedule", "progress", "overview", "topic", "subject", "notifications");
  };

  return (
    <QueryBoundary query={activity} loadingLabel="Starting activity">
      {({ recommendation, materials, questions }) => (
        <div className="space-y-6">
          <PageHeader
            kicker={`${ACTIVITY_LABEL[recommendation.activity_type]} · ${recommendation.duration_minutes} min`}
            title={recommendation.topic_name}
          />
          <p className="max-w-prose text-ink-soft">{ACTIVITY_HELP[recommendation.activity_type]}</p>
          {recommendation.activity_type !== "quiz" && recommendation.activity_type !== "practice" && (
            <section aria-labelledby="mat-heading">
              <h2 id="mat-heading" className="label mb-2 !text-base">
                Materials
              </h2>
              <Materials items={materials} />
            </section>
          )}
          {questions.length === 0 ? (
            <ReviewDone recommendationId={recommendation.id} />
          ) : (
            <QuestionRunner
              questions={questions}
              submit={(answers) => post<SubmitResult>(`/recommendations/${recommendation.id}/submit`, { answers })}
              onFinished={refresh}
              doneAction={<LinkButton to="/today">Back to today</LinkButton>}
            />
          )}
          {!finished && (
            <div className="space-y-2 border-t border-line pt-4">
              <FormError message={skipError} />
              <Button variant="ghost" loading={skip.isPending} onClick={() => skip.mutate()}>
                Skip this activity
              </Button>
            </div>
          )}
        </div>
      )}
    </QueryBoundary>
  );
}
