import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import { put, request, type Material, type Topic, type UnsortedSection } from "../lib/api";
import { Button, QueryBoundary, SectionTitle, errorMessage, useInvalidate, useToast } from "./ui";

function UnsortedRow({ section, topics }: { section: UnsortedSection; topics: Topic[] }) {
  const invalidate = useInvalidate();
  const toast = useToast();
  const assign = useMutation({
    mutationFn: (topicId: number) => put(`/materials/${section.material_id}/sections/${section.id}`, { topic_id: topicId }),
    onSuccess: () => invalidate("unsorted"),
    onError: (caught) => toast(errorMessage(caught), "error"),
  });
  const label = section.title || "Untitled part";
  return (
    <li className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="break-words font-semibold">{label}</p>
        <p className="num text-sm text-ink-soft">
          {section.material_title}
          {section.page !== null && ` · page ${section.page}`} · {section.word_count} words
        </p>
      </div>
      <select
        aria-label={`Topic for ${label}`}
        className="min-h-11 border-2 border-ink bg-paper px-2 sm:w-64"
        value=""
        disabled={assign.isPending}
        onChange={(event) => assign.mutate(Number(event.target.value))}
      >
        <option value="" disabled>
          Choose a topic…
        </option>
        {topics.map((topic) => (
          <option key={topic.id} value={topic.id}>
            {topic.name}
          </option>
        ))}
      </select>
    </li>
  );
}

export function SubjectLessons({ subjectId, topics }: { subjectId: number; topics: Topic[] }) {
  const invalidate = useInvalidate();
  const toast = useToast();
  const fileInput = useRef<HTMLInputElement>(null);
  const unsorted = useQuery({
    queryKey: ["unsorted", subjectId],
    queryFn: () => request<UnsortedSection[]>(`/subjects/${subjectId}/unsorted`),
  });
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("subject_id", String(subjectId));
      form.append("file", file);
      return request<Material>("/materials/upload", { method: "POST", body: form });
    },
    onSuccess: async (material) => {
      const status = material.extraction_status;
      toast(status === "ok" ? "Lesson read and sorted into topics" : "Lesson saved, but its text could not be read", status === "ok" ? "ok" : "error");
      await invalidate("unsorted", "materials", "subject", "topic", "overview");
    },
    onError: (caught) => toast(errorMessage(caught), "error"),
  });
  return (
    <section aria-labelledby="lessons-heading">
      <SectionTitle
        action={
          <Button variant="secondary" loading={upload.isPending} onClick={() => fileInput.current?.click()}>
            Upload a lesson
          </Button>
        }
      >
        <span id="lessons-heading">Lessons</span>
      </SectionTitle>
      <input
        ref={fileInput}
        type="file"
        className="sr-only"
        tabIndex={-1}
        aria-label="Choose a lesson file"
        accept=".pdf,.docx,.pptx,.txt,.md,.png,.jpg,.jpeg"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) upload.mutate(file);
        }}
      />
      <p className="mb-3 max-w-prose text-sm text-ink-soft">
        Upload slides, handouts or notes for the whole subject. The app reads the text and files each part under the matching topic. Only you can see your files.
      </p>
      <QueryBoundary query={unsorted}>
        {(sections) =>
          sections.length === 0 ? null : (
            <div className="border-2 border-ink bg-paper-2 p-4">
              <h3 className="text-2xl">Needs a topic ({sections.length})</h3>
              <p className="text-sm text-ink-soft">These parts did not clearly match a topic. Pick one for each.</p>
              {topics.length === 0 ? (
                <p className="mt-2 font-semibold">Add a topic first.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {sections.map((section) => (
                    <UnsortedRow key={section.id} section={section} topics={topics} />
                  ))}
                </ul>
              )}
            </div>
          )
        }
      </QueryBoundary>
    </section>
  );
}
