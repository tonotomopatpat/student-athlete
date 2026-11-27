import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { BrandName } from "../components/Brand";
import { Button, FormError, TextInput, errorMessage } from "../components/ui";
import { post, type User } from "../lib/api";
import { useMe } from "../lib/auth";

function AuthLayout({ title, intro, children }: { title: string; intro: string; children: React.ReactNode }) {
  return (
    <main className="mx-auto grid min-h-dvh max-w-5xl items-center gap-10 px-5 py-10 lg:grid-cols-2">
      <section className="space-y-5">
        <BrandName />
        <h1 className="text-6xl lg:text-7xl">Train hard.<br />Study smart.</h1>
        <p className="max-w-md text-lg text-ink-soft">{intro}</p>
      </section>
      <section aria-labelledby="auth-title" className="border-2 border-ink bg-paper p-6">
        <h2 id="auth-title" className="mb-5 text-4xl">
          {title}
        </h2>
        {children}
      </section>
    </main>
  );
}

function useAuthSubmit(path: string) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const destination = (location.state as { from?: string } | null)?.from ?? "/today";
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => post<User>(path, payload),
    onSuccess: (user) => {
      client.clear();
      client.setQueryData(["me"], user);
      navigate(destination, { replace: true });
    },
  });
}

export function LoginPage() {
  const me = useMe();
  const login = useAuthSubmit("/auth/login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  if (me.data) return <Navigate to="/today" replace />;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate({ email, password });
  };
  return (
    <AuthLayout title="Sign in" intro="Your study plan, built around practice, games and class.">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <FormError message={login.isError ? errorMessage(login.error) : null} />
        <TextInput label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <TextInput
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" loading={login.isPending} className="w-full" disabled={!email || !password}>
          Sign in
        </Button>
      </form>
      <p className="mt-5">
        New here?{" "}
        <Link to="/register" className="font-semibold underline underline-offset-4">
          Create an account
        </Link>
      </p>
    </AuthLayout>
  );
}

export function RegisterPage() {
  const me = useMe();
  const register = useAuthSubmit("/auth/register");
  const [form, setForm] = useState({ name: "", email: "", sport: "", password: "" });
  if (me.data) return <Navigate to="/today" replace />;
  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));
  const passwordError = form.password.length > 0 && form.password.length < 8 ? "Use at least 8 characters." : undefined;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    register.mutate({ ...form, sport: form.sport.trim() || null });
  };
  return (
    <AuthLayout title="Create account" intro="Tell Sideline when you train and attend class. It plans study time around both.">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <FormError message={register.isError ? errorMessage(register.error) : null} />
        <TextInput label="Full name" autoComplete="name" required value={form.name} onChange={set("name")} />
        <TextInput label="Email" type="email" autoComplete="email" required value={form.email} onChange={set("email")} />
        <TextInput label="Sport (optional)" value={form.sport} onChange={set("sport")} placeholder="e.g. Basketball" />
        <TextInput
          label="Password"
          type="password"
          autoComplete="new-password"
          required
          value={form.password}
          onChange={set("password")}
          hint="At least 8 characters."
          error={passwordError}
        />
        <Button
          type="submit"
          loading={register.isPending}
          className="w-full"
          disabled={!form.name.trim() || !form.email || form.password.length < 8}
        >
          Create account
        </Button>
      </form>
      <p className="mt-5">
        Already have an account?{" "}
        <Link to="/login" className="font-semibold underline underline-offset-4">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
