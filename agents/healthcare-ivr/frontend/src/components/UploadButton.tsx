import { useRef, type ChangeEvent } from 'react'
import { useNavigate } from 'react-router'

import { useUploadRecording } from '../api/queries'
import { buttonStyles } from '../utils/ui'

export function UploadButton() {
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const upload = useUploadRecording()

  function handleFileChosen(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = '' // let the same file be chosen again after an error
    if (!file) return
    upload.mutate(file, { onSuccess: (call) => navigate(`/calls/${call.id}`) })
  }

  return (
    <div className="flex items-center gap-3">
      {upload.isError && (
        <p role="alert" className="max-w-56 text-right text-sm text-danger">
          {upload.error.message}
        </p>
      )}
      <input
        ref={inputRef}
        type="file"
        accept="audio/*,video/mp4,video/webm"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={handleFileChosen}
      />
      <button
        type="button"
        className={buttonStyles.primary}
        disabled={upload.isPending}
        onClick={() => inputRef.current?.click()}
      >
        {upload.isPending ? 'Uploading…' : 'Upload recording'}
      </button>
    </div>
  )
}
