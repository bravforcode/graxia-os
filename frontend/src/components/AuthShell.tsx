import type { ReactNode } from 'react'

type AuthShellProps = {
  title: string
  subtitle: string
  children: ReactNode
}

export function AuthShell({ title, subtitle, children }: AuthShellProps) {
  return (
    <div className="relative min-h-screen flex items-center justify-center bg-black px-4 sm:px-6 lg:px-8">
      <a href="#auth-content" className="skip-link">
        Skip to authentication form
      </a>
      <main id="auth-content" className="w-full max-w-sm space-y-8">
        <div className="text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-white">
            {title}
          </h1>
          <p className="mt-2 text-sm text-zinc-400">
            {subtitle}
          </p>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-black p-6 sm:p-8 shadow-sm">
          {children}
        </div>
      </main>
    </div>
  )
}
