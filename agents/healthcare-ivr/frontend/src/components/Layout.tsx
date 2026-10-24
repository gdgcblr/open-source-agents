import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router'

const NAV_ITEMS = [
  { to: '/calls', label: 'Calls' },
  { to: '/appointments', label: 'Appointments' },
  { to: '/hospital', label: 'Hospital' },
]

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return `block rounded-md px-3 py-1.5 text-sm font-semibold ${
    isActive ? 'bg-surface-muted text-ink' : 'text-ink-muted hover:text-ink'
  }`
}

function BrandMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 32 32" className="size-7 shrink-0">
      {/* A miniature speaker timeline: two lanes of turns and a playhead. */}
      <rect width="32" height="32" rx="7" fill="var(--ink)" />
      <rect x="5" y="9" width="11" height="4" rx="2" fill="var(--speaker-1)" />
      <rect x="23" y="9" width="4" height="4" rx="2" fill="var(--speaker-1)" />
      <rect x="13" y="19" width="13" height="4" rx="2" fill="var(--speaker-2)" />
      <rect x="18.5" y="6" width="1.5" height="20" rx="0.75" fill="var(--page)" />
    </svg>
  )
}

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh">
      <a
        href="#main"
        className="sr-only rounded-md bg-surface px-3 py-2 focus:not-sr-only focus:absolute focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link to="/" className="flex min-w-0 items-center gap-3 font-semibold">
            <BrandMark />
            {/* Visible from the sm breakpoint; screen readers always get the name. */}
            <span className="sr-only sm:not-sr-only">Hospital Reception IVR</span>
          </Link>
          <nav aria-label="Main">
            <ul className="flex items-center gap-1">
              {NAV_ITEMS.map((item) => (
                <li key={item.to}>
                  <NavLink to={item.to} className={navLinkClass}>
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
        {children}
      </main>
    </div>
  )
}
