import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { post, put, type Commitment, type CommitmentKind, type Requirement } from "../lib/api";
import { toDateInput } from "../lib/time";
import { Button, Dialog, FormError, SelectInput, TextInput, errorMessage, useInvalidate, useToast } from "./ui";

export const KIND_OPTIONS: { value: CommitmentKind; label: string }[] = [
  { value: "class", label: "Class" },
  { value: "training", label: "Training" },
  { value: "competition", label: "Game day" },
  { value: "exam", label: "Exam" },
  { value: "travel", label: "Travel" },
  { value: "other", label: "Other" },
];

const timePart = (iso: string) => iso.slice(11, 16);
const datePart = (iso: string) => iso.slice(0, 10);

interface CommitmentDialogProps {
  open: boolean;
  onClose: () => void;
  initial?: Commitment;
}

export function CommitmentDialog({ open, onClose, initial }: CommitmentDialogProps) {
  const invalidate = useInvalidate();
  const toast = useToast();
  const [title, setTitle] = useState(initial?.title ?? "");
  const [kind, setKind] = useState<CommitmentKind>(initial?.kind ?? "training");
  const [date, setDate] = useState(initial ? datePart(initial.start_at) : toDateInput(new Date()));
  const [start, setStart] = useState(initial ? timePart(initial.start_at) : "16:00");
  const [end, setEnd] = useState(initial ? timePart(initial.end_at) : "18:00");
  const [weekly, setWeekly] = useState(initial?.repeat_weekly ?? false);
  const [until, setUntil] = useState(initial?.repeat_until ?? "");
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => {
      const body = {
        title,
        kind,
        start_at: `${date}T${start}:00`,
        end_at: `${date}T${end}:00`,
        repeat_weekly: weekly,
        repeat_until: weekly && until ? until : null,
      };
      return initial ? put<Commitment>(`/commitments/${initial.id}`, body) : post<Commitment>("/commitments", body);
    },
    onSuccess: async () => {
      toast(initial ? "Commitment updated" : "Commitment added");
      await invalidate("schedule", "commitments", "recommendation");
      onClose();
    },
    onError: (caught) => setError(errorMessage(caught)),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (end <= start) {
      setError("End time must be after the start time.");
      return;
    }
    save.mutate();
  };

  return (
    <Dialog open={open} onClose={onClose} title={initial ? "Edit commitment" : "Add commitment"}>
      <form onSubmit={submit} className="space-y-4">
        <TextInput label="Title" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={160} />
        <SelectInput label="Type" value={kind} onChange={(e) => setKind(e.target.value as CommitmentKind)}>
          {KIND_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </SelectInput>
        <TextInput label={weekly ? "First date" : "Date"} type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
        <div className="grid grid-cols-2 gap-3">
          <TextInput label="Starts" type="time" value={start} onChange={(e) => setStart(e.target.value)} required />
          <TextInput label="Ends" type="time" value={end} onChange={(e) => setEnd(e.target.value)} required />
        </div>
        <label className="flex min-h-11 items-center gap-3">
          <input type="checkbox" className="size-5 accent-ink" checked={weekly} onChange={(e) => setWeekly(e.target.checked)} />
          <span className="font-semibold">Repeats every week</span>
        </label>
        {weekly && (
          <TextInput
            label="Repeat until (optional)"
            type="date"
            min={date}
            value={until}
            onChange={(e) => setUntil(e.target.value)}
          />
        )}
        <FormError message={error} />
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            Save
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function RequirementDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const invalidate = useInvalidate();
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(toDateInput(new Date()));
  const [time, setTime] = useState("17:00");
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => post<Requirement>("/requirements", { title, due_at: `${date}T${time}:00` }),
    onSuccess: async () => {
      setTitle("");
      toast("Deadline added");
      await invalidate("schedule", "requirements", "recommendation");
      onClose();
    },
    onError: (caught) => setError(errorMessage(caught)),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    save.mutate();
  };
  return (
    <Dialog open={open} onClose={onClose} title="Add deadline">
      <form onSubmit={submit} className="space-y-4">
        <TextInput label="What is due" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={160} />
        <div className="grid grid-cols-2 gap-3">
          <TextInput label="Due date" type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
          <TextInput label="Due time" type="time" value={time} onChange={(e) => setTime(e.target.value)} required />
        </div>
        <FormError message={error} />
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            Save
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
