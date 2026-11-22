"use client";

import { useState } from "react";
import Link from "next/link";

const field = "mt-2 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2.5 text-base text-slate-50";

export default function AuthForm({ mode }) {
  const registering = mode === "register";
  const title = registering ? "Create an account" : "Sign in";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    if (busy) return;

    const form = new FormData(event.currentTarget);
    const email = form.get("email").trim();
    const password = form.get("password");
    if (registering && password !== form.get("confirmation")) {
      setError("The passwords don’t match.");
      return;
    }

    setError("");
    setBusy(true);
    try {
      const response = await fetch("/api/auth/" + mode, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (response.ok) {
        window.location.replace("/");
        return;
      }
      const payload = await response.json().catch(() => ({}));
      const validation = payload.details?.email?.[0] || payload.details?.password?.[0];
      setError(validation || payload.message || "The request could not be completed. Please try again.");
    } catch {
      setError("Could not reach Finance Agent. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-dvh">
      <header className="border-b border-slate-800">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-8">
          <Link href="/" className="text-base font-semibold tracking-tight">Finance Agent</Link>
        </div>
      </header>
      <main className="mx-auto max-w-sm px-4 pb-12 pt-12 sm:pt-20" aria-labelledby="auth-title">
        <h1 id="auth-title" className="text-3xl font-semibold tracking-tight">{title}</h1>
        <form onSubmit={submit} className="mt-7 space-y-5">
          <div>
            <label htmlFor="email" className="block text-sm font-medium">Email address</label>
            <input id="email" name="email" type="email" autoComplete="username" autoCapitalize="none"
              spellCheck={false} required className={field} />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium">Password</label>
            <input id="password" name="password" type="password" required className={field}
              minLength={registering ? 8 : undefined} aria-describedby={registering ? "password-help" : undefined}
              autoComplete={registering ? "new-password" : "current-password"} />
            {registering && <p id="password-help" className="mt-2 text-sm text-slate-400">At least 8 characters.</p>}
          </div>

          {registering && (
            <div>
              <label htmlFor="confirmation" className="block text-sm font-medium">Confirm password</label>
              <input id="confirmation" name="confirmation" type="password" autoComplete="new-password" required className={field} />
            </div>
          )}

          {error && <p role="alert" className="rounded-md border border-rose-900 px-3 py-2 text-sm text-rose-300">{error}</p>}
          <button type="submit" disabled={busy}
            className="w-full rounded-md bg-slate-100 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-white disabled:opacity-60">
            {busy ? (registering ? "Creating account…" : "Signing in…") : title}
          </button>
        </form>

        <p className="mt-6 border-t border-slate-800 pt-5 text-sm text-slate-400">
          {registering ? "Already have an account? " : "New to Finance Agent? "}
          <Link href={registering ? "/login" : "/register"} className="font-medium text-sky-300 hover:underline">
            {registering ? "Sign in" : "Create an account"}
          </Link>
        </p>
      </main>
    </div>
  );
}
