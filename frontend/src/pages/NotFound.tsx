import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
      <p className="text-6xl font-semibold text-[var(--color-text-tertiary,#6b7280)]">404</p>
      <h1 className="text-xl font-medium">Page not found</h1>
      <p className="text-sm text-[var(--color-text-secondary,#9ca3af)]">
        This route doesn't exist in Graxia OS.
      </p>
      <Link
        to="/"
        className="mt-2 rounded-md bg-[var(--color-accent,#06b6d4)] px-4 py-2 text-sm font-semibold text-slate-950 hover:opacity-90"
      >
        Back to dashboard
      </Link>
    </main>
  );
}
