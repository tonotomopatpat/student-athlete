import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Button, FormError, PageHeader, SectionTitle, SelectInput, TextInput, errorMessage, useToast } from "../components/ui";
import { patch, type User } from "../lib/api";
import { useMe, useSignOut } from "../lib/auth";
import { clockToMinutes, minutesToClock } from "../lib/time";
import { currentPushState, disablePush, enablePush, type PushState } from "../lib/push";

const REMINDER_OPTIONS = [5, 10, 15, 30, 60];

function SettingsForm({ user }: { user: User }) {
  const client = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState(user.name);
  const [sport, setSport] = useState(user.sport ?? "");
  const [windowStart, setWindowStart] = useState(minutesToClock(user.study_window_start));
  const [windowEnd, setWindowEnd] = useState(minutesToClock(user.study_window_end === 1440 ? 1439 : user.study_window_end));
  const [buffer, setBuffer] = useState(String(user.buffer_minutes));
  const [reminder, setReminder] = useState(String(user.reminder_minutes));
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () =>
      patch<User>("/auth/me", {
        name,
        sport,
        study_window_start: clockToMinutes(windowStart),
        study_window_end: clockToMinutes(windowEnd),
        buffer_minutes: Number(buffer),
        reminder_minutes: Number(reminder),
      }),
    onSuccess: (updated) => {
      client.setQueryData(["me"], updated);
      void client.invalidateQueries({ queryKey: ["schedule"] });
      void client.invalidateQueries({ queryKey: ["recommendation"] });
      toast("Settings saved");
    },
    onError: (caught) => setError(errorMessage(caught)),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (clockToMinutes(windowEnd) - clockToMinutes(windowStart) < 60) {
      setError("Your study hours must span at least one hour.");
      return;
    }
    save.mutate();
  };
  const reminderOptions = REMINDER_OPTIONS.includes(user.reminder_minutes) ? REMINDER_OPTIONS : [...REMINDER_OPTIONS, user.reminder_minutes].sort((a, b) => a - b);
  return (
    <form onSubmit={submit} className="space-y-4">
      <TextInput label="Name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} />
      <TextInput label="Sport" value={sport} onChange={(e) => setSport(e.target.value)} maxLength={80} />
      <div className="grid grid-cols-2 gap-3">
        <TextInput label="Study from" type="time" value={windowStart} onChange={(e) => setWindowStart(e.target.value)} required />
        <TextInput label="Study until" type="time" value={windowEnd} onChange={(e) => setWindowEnd(e.target.value)} required />
      </div>
      <TextInput
        label="Gap around commitments (minutes)"
        hint="Study sessions keep this much distance from classes, training and games."
        type="number"
        min={0}
        max={120}
        step={5}
        value={buffer}
        onChange={(e) => setBuffer(e.target.value)}
        required
      />
      <SelectInput label="Remind me before a session" value={reminder} onChange={(e) => setReminder(e.target.value)}>
        {reminderOptions.map((minutes) => (
          <option key={minutes} value={minutes}>
            {minutes} minutes before
          </option>
        ))}
      </SelectInput>
      <FormError message={error} />
      <Button type="submit" loading={save.isPending}>
        Save settings
      </Button>
    </form>
  );
}

const PUSH_COPY: Record<PushState, string> = {
  unsupported: "This browser does not support push notifications. Reminders still appear under Alerts.",
  blocked: "Notifications are blocked for this site. Allow them in your browser settings to turn this on.",
  off: "Get a reminder on this device before a study session, even when the app is closed.",
  on: "Reminders are on for this device.",
};

function PushControl() {
  const toast = useToast();
  const [override, setOverride] = useState<PushState | null>(null);
  const state = useQuery({ queryKey: ["push-state"], queryFn: currentPushState, staleTime: 0 });
  const toggle = useMutation({
    mutationFn: (current: PushState) => (current === "on" ? disablePush() : enablePush()),
    onSuccess: setOverride,
    onError: (caught) => toast(errorMessage(caught), "error"),
  });
  if (state.isPending) return <p role="status">Checking…</p>;
  const current = override ?? state.data ?? "unsupported";
  return (
    <div className="space-y-3">
      <p className="max-w-prose">{PUSH_COPY[current]}</p>
      {(current === "on" || current === "off") && (
        <Button variant={current === "on" ? "secondary" : "primary"} loading={toggle.isPending} onClick={() => toggle.mutate(current)}>
          {current === "on" ? "Turn off reminders" : "Turn on reminders"}
        </Button>
      )}
    </div>
  );
}

export function MePage() {
  const me = useMe();
  const signOut = useSignOut();
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);
  const leave = async () => {
    setSigningOut(true);
    try {
      await signOut();
      navigate("/login", { replace: true });
    } finally {
      setSigningOut(false);
    }
  };
  if (!me.data) return null;
  return (
    <div className="space-y-8">
      <PageHeader title="Me" kicker={me.data.email} />
      <section aria-labelledby="settings-heading">
        <SectionTitle>
          <span id="settings-heading">Study settings</span>
        </SectionTitle>
        <SettingsForm user={me.data} />
      </section>
      <section aria-labelledby="push-heading">
        <SectionTitle>
          <span id="push-heading">Reminders on this device</span>
        </SectionTitle>
        <PushControl />
      </section>
      <section>
        <Button variant="danger" loading={signingOut} onClick={() => void leave()}>
          Sign out
        </Button>
      </section>
    </div>
  );
}
