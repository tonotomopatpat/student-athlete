import { useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../lib/api";

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Please try again.";
}

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const buttonBase =
  "inline-flex min-h-11 items-center whitespace-nowrap justify-center gap-2 px-4 py-2 font-display text-lg font-semibold uppercase tracking-wide transition-colors disabled:opacity-50";
const buttonVariants: Record<ButtonVariant, string> = {
  primary: "bg-ink text-paper hover:bg-ink-soft",
  secondary: "border-2 border-ink text-ink hover:bg-paper-2",
  ghost: "text-ink underline decoration-2 underline-offset-4 hover:bg-paper-2",
  danger: "border-2 border-flag text-flag hover:bg-flag-soft",
};

export function buttonClass(variant: ButtonVariant = "primary", extra = ""): string {
  return `${buttonBase} ${buttonVariants[variant]} ${extra}`;
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  loading?: boolean;
}

export function Button({ variant = "primary", loading = false, className = "", children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      type={rest.type ?? "button"}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={buttonClass(variant, className)}
    >
      {loading ? "Working…" : children}
    </button>
  );
}

export function LinkButton({
  to,
  variant = "primary",
  className = "",
  children,
}: {
  to: string;
  variant?: ButtonVariant;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link to={to} className={buttonClass(variant, className)}>
      {children}
    </Link>
  );
}

const controlClass =
  "w-full min-h-11 border-2 border-ink bg-paper px-3 py-2 text-base text-ink placeholder:text-ink-soft/70 disabled:opacity-60";

interface FieldProps {
  label: string;
  hint?: string;
  error?: string;
  children: (props: { id: string; describedBy: string | undefined; invalid: boolean }) => ReactNode;
}

export function Field({ label, hint, error, children }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="label block">
        {label}
      </label>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {hint && (
        <p id={hintId} className="text-sm text-ink-soft">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-sm font-semibold text-flag">
          {error}
        </p>
      )}
    </div>
  );
}

export function TextInput({
  label,
  hint,
  error,
  ...rest
}: { label: string; hint?: string; error?: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <Field label={label} hint={hint} error={error}>
      {({ id, describedBy, invalid }) => (
        <input {...rest} id={id} aria-describedby={describedBy} aria-invalid={invalid || undefined} className={controlClass} />
      )}
    </Field>
  );
}

export function TextArea({
  label,
  hint,
  error,
  ...rest
}: { label: string; hint?: string; error?: string } & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <Field label={label} hint={hint} error={error}>
      {({ id, describedBy, invalid }) => (
        <textarea
          {...rest}
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          className={`${controlClass} min-h-28`}
        />
      )}
    </Field>
  );
}

export function SelectInput({
  label,
  hint,
  error,
  children,
  ...rest
}: { label: string; hint?: string; error?: string } & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <Field label={label} hint={hint} error={error}>
      {({ id, describedBy, invalid }) => (
        <select {...rest} id={id} aria-describedby={describedBy} aria-invalid={invalid || undefined} className={controlClass}>
          {children}
        </select>
      )}
    </Field>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="border-l-4 border-flag bg-flag-soft px-3 py-2 font-semibold text-flag">
      {message}
    </p>
  );
}

export function Dialog({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
      className="m-auto w-[min(32rem,calc(100vw-1.5rem))] max-h-[92dvh] overflow-y-auto border-2 border-ink bg-paper p-0 text-ink"
    >
      {open && (
        <div className="space-y-4 p-5">
          <div className="flex items-start justify-between gap-4">
            <h2 id={titleId} className="text-3xl">
              {title}
            </h2>
            <button type="button" onClick={onClose} className="min-h-11 min-w-11 text-2xl leading-none" aria-label="Close dialog">
              ×
            </button>
          </div>
          {children}
        </div>
      )}
    </dialog>
  );
}

interface ToastItem {
  id: number;
  message: string;
  tone: "ok" | "error";
}

const ToastContext = createContext<(message: string, tone?: "ok" | "error") => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const counter = useRef(0);
  const push = useCallback((message: string, tone: "ok" | "error" = "ok") => {
    const id = ++counter.current;
    setItems((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => setItems((current) => current.filter((item) => item.id !== id)), 5000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-24 z-50 flex flex-col items-center gap-2 px-3 lg:bottom-6">
        {items.map((item) => (
          <p
            key={item.id}
            role={item.tone === "error" ? "alert" : "status"}
            className={`pointer-events-auto max-w-md border-2 px-4 py-2 font-semibold ${
              item.tone === "error" ? "border-flag bg-flag-soft text-flag" : "border-ink bg-ink text-paper"
            }`}
          >
            {item.message}
          </p>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden className={`animate-pulse bg-paper-2 ${className}`} />;
}

export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-3 py-2">
      <Skeleton className="h-6 w-1/3" />
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-20 w-full" />
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="border-2 border-dashed border-line px-5 py-8">
      <h3 className="text-2xl">{title}</h3>
      {children && <p className="mt-2 max-w-prose text-ink-soft">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div role="alert" className="border-2 border-flag bg-flag-soft px-5 py-6">
      <h3 className="text-2xl text-flag">That did not load</h3>
      <p className="mt-1 text-ink">{errorMessage(error)}</p>
      {onRetry && (
        <Button variant="secondary" className="mt-4" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function QueryBoundary<T>({
  query,
  children,
  loadingLabel,
}: {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
  loadingLabel?: string;
}) {
  if (query.isPending) return <LoadingBlock label={loadingLabel} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  return <>{children(query.data)}</>;
}

export function PageHeader({ title, kicker, action }: { title: string; kicker?: string; action?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3 border-b-2 border-ink pb-3">
      <div>
        {kicker && <p className="label">{kicker}</p>}
        <h1 className="text-5xl">{title}</h1>
      </div>
      {action}
    </header>
  );
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="label !text-base">{children}</h2>
      {action}
    </div>
  );
}

export function Mastery({ value, label }: { value: number | null; label?: string }) {
  const percent = value === null ? 0 : Math.round(value * 100);
  const text = value === null ? "Not assessed" : `${percent}%`;
  return (
    <div className="flex items-center gap-3">
      <div
        role="meter"
        aria-label={label ?? "Mastery"}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={text}
        className="relative h-3 min-w-24 flex-1 bg-paper-2 outline outline-1 outline-line"
      >
        <div className={`h-full ${percent >= 95 ? "bg-pitch" : "bg-ink"}`} style={{ width: `${percent}%` }} />
        <div className="absolute inset-y-[-3px] left-[95%] w-0.5 bg-flag" title="Mastery threshold (95%)" />
      </div>
      <span className="num w-24 shrink-0 text-right font-display text-xl font-semibold">{text}</span>
    </div>
  );
}

export function Chip({ children, tone = "plain" }: { children: ReactNode; tone?: "plain" | "go" | "warn" | "done" }) {
  const tones = {
    plain: "border-ink-soft text-ink-soft",
    go: "border-ink bg-whistle text-ink",
    warn: "border-flag bg-flag-soft text-flag",
    done: "border-pitch bg-pitch-soft text-pitch",
  };
  return (
    <span className={`inline-block border px-2 py-0.5 font-display text-sm font-semibold uppercase tracking-wider ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function useInvalidate() {
  const client = useQueryClient();
  return useMemo(
    () => (...keys: string[]) => Promise.all(keys.map((key) => client.invalidateQueries({ queryKey: [key] }))),
    [client],
  );
}

export const ACTIVITY_LABEL: Record<string, string> = {
  review_material: "Review",
  practice: "Practice",
  quiz: "Quiz",
  revisit: "Revisit",
};

export const ACTIVITY_HELP: Record<string, string> = {
  review_material: "Read your materials for this topic.",
  practice: "A short set of questions with explanations.",
  quiz: "A longer check of what you know.",
  revisit: "Re-read your materials, then answer a few questions.",
};
