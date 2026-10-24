import { Children, useState, type ReactNode } from 'react'
import Markdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { useHospitalInfo } from '../api/queries'
import { DoctorsEditor } from '../components/DoctorsEditor'
import { DoctorsTable } from '../components/DoctorsTable'
import { HospitalInfoEditor } from '../components/HospitalInfoEditor'
import { PerformanceSection } from '../components/PerformanceSection'
import { sectionsOf, slugify } from '../utils/markdown'
import { buttonStyles } from '../utils/ui'

function plainText(children: ReactNode): string {
  return Children.toArray(children)
    .map((child) => (typeof child === 'string' || typeof child === 'number' ? String(child) : ''))
    .join('')
}

const markdownComponents: Components = {
  // Anchor targets for the outline; scroll margin keeps headings clear of the viewport edge.
  h2: ({ children }) => (
    <h2 id={slugify(plainText(children))} className="scroll-mt-6">
      {children}
    </h2>
  ),
  // Wide tables scroll inside the article instead of the page on phones.
  table: ({ children }) => (
    <div className="overflow-x-auto">
      <table>{children}</table>
    </div>
  ),
}

const PERFORMANCE_SECTION = { id: 'performance', title: 'Performance' }
const INFORMATION_SECTION = { id: 'information', title: 'Information' }
const DOCTORS_SECTION = { id: 'doctors-and-opd-schedule', title: 'Doctors and OPD schedule' }
const cardClass = 'rounded-xl border border-line bg-surface px-5 py-6 sm:px-8 sm:py-8'

export function HospitalPage() {
  const { data, error, isPending } = useHospitalInfo()
  const [editing, setEditing] = useState<'information' | 'doctors' | null>(null)

  if (isPending) {
    return <p className="text-ink-muted">Loading hospital information…</p>
  }

  if (error) {
    return (
      <p role="alert" className="rounded-lg border border-line bg-surface px-4 py-3">
        Couldn’t load the hospital information. {error.message}
      </p>
    )
  }

  const sections = [
    PERFORMANCE_SECTION,
    ...(editing === 'information' ? [INFORMATION_SECTION] : sectionsOf(data.markdown)),
    DOCTORS_SECTION,
  ]

  return (
    <>
      <title>{`${data.name} – Hospital Reception IVR`}</title>
      {/* minmax(0, 1fr) stops wide tables from stretching the column past the screen. */}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-8 lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-12">
        <aside className="lg:sticky lg:top-8 lg:self-start">
          <p className="rounded-lg border border-line bg-surface px-4 py-3 text-sm text-ink-muted">
            The receptionist answers callers from the information and doctors on this page.
            Saved changes apply from the next call.
          </p>
          <nav aria-label="On this page" className="mt-6 hidden lg:block">
            <h2 className="text-sm font-semibold">On this page</h2>
            <ul className="mt-2 space-y-1 border-l border-line text-sm">
              {sections.map((section) => (
                <li key={section.id}>
                  <a
                    href={`#${section.id}`}
                    className="-ml-px block border-l border-transparent py-1 pl-3 text-ink-muted hover:border-ink hover:text-ink"
                  >
                    {section.title}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </aside>

        <div className="space-y-8">
          <PerformanceSection />

          <section aria-label="Hospital information" className={cardClass}>
            {editing === 'information' ? (
              <>
                <h2 id={INFORMATION_SECTION.id} className="scroll-mt-6 text-xl font-bold">
                  Edit information
                </h2>
                <div className="mt-4">
                  <HospitalInfoEditor
                    name={data.name}
                    markdown={data.markdown}
                    onDone={() => setEditing(null)}
                  />
                </div>
              </>
            ) : (
              <>
                <div className="flex justify-end">
                  <button
                    type="button"
                    className={buttonStyles.secondary}
                    onClick={() => setEditing('information')}
                  >
                    Edit information
                  </button>
                </div>
                <article className="prose prose-theme max-w-none">
                  <Markdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                    {data.markdown}
                  </Markdown>
                </article>
              </>
            )}
          </section>

          <section aria-labelledby={DOCTORS_SECTION.id} className={cardClass}>
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h2 id={DOCTORS_SECTION.id} className="scroll-mt-6 text-xl font-bold">
                {DOCTORS_SECTION.title}
              </h2>
              {editing !== 'doctors' && (
                <button
                  type="button"
                  className={buttonStyles.secondary}
                  onClick={() => setEditing('doctors')}
                >
                  Edit doctors
                </button>
              )}
            </div>
            <p className="mt-1 text-sm text-ink-muted">
              The receptionist books appointments in these OPD slots. Doctors with upcoming
              appointments can’t be removed until those are cancelled.
            </p>
            <div className="mt-4">
              {editing === 'doctors' ? (
                <DoctorsEditor doctors={data.doctors} onDone={() => setEditing(null)} />
              ) : (
                <DoctorsTable doctors={data.doctors} />
              )}
            </div>
          </section>
        </div>
      </div>
    </>
  )
}
