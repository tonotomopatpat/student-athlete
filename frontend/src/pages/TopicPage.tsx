import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { TopicMaterials } from "../components/TopicMaterials";
import { TopicQuestions } from "../components/TopicQuestions";
import { LinkButton, Mastery, PageHeader, QueryBoundary } from "../components/ui";
import { request, type SubjectDetail, type Topic } from "../lib/api";

function Action({ topic, enrolled }: { topic: Topic; enrolled: boolean }) {
  if (!enrolled) {
    return (
      <p className="border-l-4 border-whistle bg-paper-2 px-3 py-2">
        Enroll in <Link className="font-semibold underline underline-offset-4" to={`/learn/subjects/${topic.subject_id}`}>{topic.subject_name}</Link> to take quizzes here.
      </p>
    );
  }
  if (!topic.ready) {
    return (
      <p className="border-l-4 border-flag bg-flag-soft px-3 py-2" role="status">
        Add {5 - topic.question_count} more question{5 - topic.question_count === 1 ? "" : "s"} to unlock quizzes for this topic.
      </p>
    );
  }
  if (!topic.diagnostic_done) {
    return <LinkButton to={`/assessment/${topic.id}/diagnostic`}>Take the starting quiz</LinkButton>;
  }
  return <LinkButton to={`/assessment/${topic.id}/practice`}>Practice this topic</LinkButton>;
}

export function TopicPage() {
  const { topicId } = useParams();
  const topic = useQuery({ queryKey: ["topic", topicId], queryFn: () => request<Topic>(`/topics/${topicId}`) });
  const subjectId = topic.data?.subject_id;
  const subject = useQuery({
    queryKey: ["subject", String(subjectId)],
    queryFn: () => request<SubjectDetail>(`/subjects/${subjectId}`),
    enabled: subjectId !== undefined,
  });

  return (
    <QueryBoundary query={topic}>
      {(data) => (
        <div className="space-y-8">
          <Link to={`/learn/subjects/${data.subject_id}`} className="inline-block min-h-11 py-2 font-semibold underline underline-offset-4">
            ← {data.subject_name}
          </Link>
          <PageHeader title={data.name} kicker="Topic" />
          <div className="space-y-3">
            <Mastery value={data.mastery} label="Mastery" />
            {data.mastered && <p className="font-semibold text-pitch">Mastered: your estimate is at or above 95%.</p>}
            {subject.data && <Action topic={data} enrolled={subject.data.enrolled} />}
          </div>
          <TopicMaterials subjectId={data.subject_id} topicId={data.id} />
          <TopicQuestions topicId={data.id} questionCount={data.question_count} />
        </div>
      )}
    </QueryBoundary>
  );
}
