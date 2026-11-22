"use client";

export default function ApplicationError() {
  return (
    <main className="flex min-h-dvh items-center justify-center px-4">
      <section aria-labelledby="error-heading" className="w-full max-w-md rounded-xl border border-slate-800 bg-slate-900/35 p-6">
        <h1 id="error-heading" className="text-xl font-semibold">This page could not load</h1>
        <button type="button" onClick={() => window.location.reload()}
          className="mt-4 rounded-md border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800">
          Reload page
        </button>
      </section>
    </main>
  );
}
