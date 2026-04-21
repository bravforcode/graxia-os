import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = {
  children: ReactNode
}

type State = {
  hasError: boolean
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled React error', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="min-h-screen bg-[var(--color-bg-primary)] px-6 py-10 text-[var(--color-text-primary)]">
          <div className="mx-auto max-w-2xl rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-6">
            <p className="text-sm uppercase tracking-[0.24em] text-[var(--color-text-tertiary)]">Runtime guard</p>
            <h1 className="mt-3 text-2xl font-semibold">Something broke before the page could recover.</h1>
            <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">
              Refresh the app after checking the backend health and browser console.
            </p>
            <button
              type="button"
              className="mt-5 rounded-lg bg-[var(--color-accent-cyan)] px-4 py-2 text-sm font-semibold text-slate-950"
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
          </div>
        </main>
      )
    }

    return this.props.children
  }
}
