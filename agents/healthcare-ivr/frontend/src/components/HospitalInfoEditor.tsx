import { useState, type FormEvent } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { useUpdateHospitalInfo } from '../api/queries'
import { buttonStyles } from '../utils/ui'

interface HospitalInfoEditorProps {
  name: string
  markdown: string
  onDone: () => void
}

const inputClass =
  'w-full rounded-md border border-line bg-surface px-3 py-2 text-ink placeholder:text-ink-muted'

export function HospitalInfoEditor({ name, markdown, onDone }: HospitalInfoEditorProps) {
  const [draftName, setDraftName] = useState(name)
  const [draftMarkdown, setDraftMarkdown] = useState(markdown)
  const [showPreview, setShowPreview] = useState(false)
  const save = useUpdateHospitalInfo()

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    save.mutate({ name: draftName, markdown: draftMarkdown }, { onSuccess: onDone })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="hospital-name" className="text-sm font-semibold">
          Hospital name
        </label>
        <input
          id="hospital-name"
          value={draftName}
          onChange={(event) => setDraftName(event.target.value)}
          className={`mt-1 ${inputClass}`}
        />
      </div>

      <div>
        <div className="flex items-baseline justify-between gap-3">
          <label htmlFor="hospital-markdown" className="text-sm font-semibold">
            Information (Markdown)
          </label>
          <button
            type="button"
            onClick={() => setShowPreview((preview) => !preview)}
            className="text-sm font-semibold text-ink-muted hover:text-ink"
          >
            {showPreview ? 'Edit text' : 'Preview'}
          </button>
        </div>
        {showPreview ? (
          <div className="prose prose-theme mt-1 max-w-none rounded-md border border-line px-4 py-3">
            <Markdown remarkPlugins={[remarkGfm]}>{draftMarkdown}</Markdown>
          </div>
        ) : (
          <textarea
            id="hospital-markdown"
            value={draftMarkdown}
            onChange={(event) => setDraftMarkdown(event.target.value)}
            rows={22}
            spellCheck
            className={`mt-1 font-mono text-sm leading-relaxed ${inputClass}`}
          />
        )}
        <p className="mt-1 text-xs text-ink-muted">
          Use “## Heading” for sections and tables for timings. The receptionist reads this
          exactly as written.
        </p>
      </div>

      {save.isError && (
        <p role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm">
          Couldn’t save. {save.error.message}
        </p>
      )}

      <div className="flex gap-2">
        <button type="submit" className={buttonStyles.primary} disabled={save.isPending}>
          {save.isPending ? 'Saving…' : 'Save information'}
        </button>
        <button type="button" className={buttonStyles.secondary} onClick={onDone}>
          Cancel
        </button>
      </div>
    </form>
  )
}
