import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  Button,
  EmptyState,
  PageHeader,
  QueryBoundary,
  errorMessage,
  useInvalidate,
  useToast,
} from "../components/ui";
import { post, request, type Notification } from "../lib/api";
import { formatDateTime } from "../lib/time";

export function NotificationsPage() {
  const navigate = useNavigate();
  const invalidate = useInvalidate();
  const toast = useToast();
  const list = useQuery({ queryKey: ["notifications", "list"], queryFn: () => request<Notification[]>("/notifications") });
  const markRead = useMutation({
    mutationFn: (n: Notification) => post(`/notifications/${n.id}/read`),
    onSuccess: () => invalidate("notifications"),
    onError: (caught) => toast(errorMessage(caught), "error"),
  });
  const markAll = useMutation({
    mutationFn: () => post("/notifications/read-all"),
    onSuccess: () => invalidate("notifications"),
    onError: (caught) => toast(errorMessage(caught), "error"),
  });
  const open = (n: Notification) => {
    if (!n.read_at) markRead.mutate(n);
    if (n.link) navigate(n.link);
  };
  return (
    <div className="space-y-6">
      <PageHeader
        title="Alerts"
        kicker="Reminders and updates"
        action={
          <Button variant="secondary" loading={markAll.isPending} onClick={() => markAll.mutate()} disabled={!list.data?.some((n) => !n.read_at)}>
            Mark all read
          </Button>
        }
      />
      <QueryBoundary query={list}>
        {(items) =>
          items.length === 0 ? (
            <EmptyState title="No alerts yet">Study reminders and plan changes show up here.</EmptyState>
          ) : (
            <ul className="divide-y divide-line border-y-2 border-ink">
              {items.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => open(n)}
                    className={`flex min-h-14 w-full items-start gap-3 px-1 py-3 text-left hover:bg-paper-2 ${n.read_at ? "text-ink-soft" : ""}`}
                  >
                    <span
                      aria-hidden
                      className={`mt-2 size-3 shrink-0 ${n.read_at ? "border-2 border-line" : "bg-flag"}`}
                    />
                    <span className="min-w-0">
                      <span className="block font-display text-xl font-bold leading-tight">
                        {!n.read_at && <span className="sr-only">Unread: </span>}
                        {n.title}
                      </span>
                      <span className="block">{n.body}</span>
                      <span className="num block text-sm text-ink-soft">{formatDateTime(n.scheduled_for)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )
        }
      </QueryBoundary>
    </div>
  );
}
