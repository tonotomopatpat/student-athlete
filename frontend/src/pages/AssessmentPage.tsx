import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useParams } from "react-router-dom";
import { QuestionRunner } from "../components/QuestionRunner";
import { LinkButton, PageHeader, QueryBoundary, useInvalidate } from "../components/ui";
import { post, request, type QuestionPublic, type SubmitResult, type Topic } from "../lib/api";

export function AssessmentPage() {
  const { topicId, mode } = useParams();
  const invalidate = useInvalidate();
  const valid = mode === "diagnostic" || mode === "practice";
  const topic = useQuery({ queryKey: ["topic", topicId], queryFn: () => request<Topic>(`/topics/${topicId}`), enabled: valid });
  const questions = useQuery({
    queryKey: ["assessment-questions", topicId, mode],
    queryFn: () => request<QuestionPublic[]>(`/topics/${topicId}/questions?mode=${mode}&limit=5`),
    enabled: valid,
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: false,
  });
  if (!valid) return <Navigate to="/learn" replace />;

  const submit = (answers: { question_id: number; chosen_index: number }[]) =>
    post<SubmitResult>("/assessments/submit", {
      topic_id: Number(topicId),
      context: mode === "diagnostic" ? "diagnostic" : "self",
      answers,
    });

  return (
    <div className="space-y-6">
      <Link to={`/learn/topics/${topicId}`} className="inline-block min-h-11 py-2 font-semibold underline underline-offset-4">
        ← Back to topic
      </Link>
      <PageHeader title={topic.data?.name ?? "Quiz"} kicker={mode === "diagnostic" ? "Starting quiz" : "Practice"} />
      <QueryBoundary query={questions} loadingLabel="Loading questions">
        {(items) => (
          <QuestionRunner
            questions={items}
            submit={submit}
            onFinished={() => void invalidate("topic", "subject", "overview", "progress", "recommendation")}
            doneAction={
              <div className="flex flex-wrap gap-3">
                <LinkButton to="/today">Back to today</LinkButton>
                <LinkButton to={`/learn/topics/${topicId}`} variant="secondary">
                  Topic page
                </LinkButton>
              </div>
            }
          />
        )}
      </QueryBoundary>
    </div>
  );
}
