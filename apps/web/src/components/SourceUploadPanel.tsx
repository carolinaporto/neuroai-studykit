import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { generateQuestions, uploadSources } from '../api/client'
import type { GenerateResponse, UploadResult } from '../api/types'
import { filesFromDataTransferItems } from '../lib/folderUpload'
import { Button } from './Button'
import './SourceUploadPanel.css'

// Same set packages/ingest/cli.py's PARSERS supports — kept in sync by hand, mirrored here
// only so the UI can show "not supported" before spending a network round trip on it. The
// backend is still the authority: it checks this again and would reject anything that
// somehow got past this filter.
const SUPPORTED_EXTENSIONS = new Set(['.pdf', '.pptx', '.vtt', '.srt'])

function extensionOf(filename: string): string {
  const i = filename.lastIndexOf('.')
  return i === -1 ? '' : filename.slice(i).toLowerCase()
}

const RESULT_LABEL: Record<UploadResult['status'], string> = {
  ingested: 'Uploaded',
  duplicate: 'Already uploaded',
  unsupported: 'Not supported',
  too_large: 'Too large',
  failed: 'Failed',
}

export function SourceUploadPanel() {
  const queryClient = useQueryClient()
  const [week, setWeek] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [uploadResults, setUploadResults] = useState<UploadResult[] | null>(null)
  const [generateResult, setGenerateResult] = useState<GenerateResponse | null>(null)
  const [force, setForce] = useState(false)
  const folderInputRef = useRef<HTMLInputElement>(null)

  // webkitdirectory has no JSX/React prop — it has to be set imperatively on the DOM node.
  useEffect(() => {
    folderInputRef.current?.setAttribute('webkitdirectory', '')
    folderInputRef.current?.setAttribute('directory', '')
  }, [])

  const weekNumber = Number(week)
  const weekIsValid = week.trim() !== '' && !Number.isNaN(weekNumber)
  const supportedFiles = files.filter((f) => SUPPORTED_EXTENSIONS.has(extensionOf(f.name)))
  const unsupportedFiles = files.filter((f) => !SUPPORTED_EXTENSIONS.has(extensionOf(f.name)))

  const uploadMutation = useMutation({
    mutationFn: () => uploadSources(weekNumber, supportedFiles),
    onSuccess: (data) => {
      setUploadResults(data.results)
      queryClient.invalidateQueries({ queryKey: ['sources'] })
    },
  })

  const generateMutation = useMutation({
    mutationFn: () => generateQuestions(weekNumber, force),
    onSuccess: (data) => {
      setGenerateResult(data)
      queryClient.invalidateQueries({ queryKey: ['quiz-weeks'] })
    },
  })

  function resetSelection(nextFiles: File[]) {
    setFiles(nextFiles)
    setUploadResults(null)
  }

  async function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setIsDragging(false)
    resetSelection(await filesFromDataTransferItems(e.dataTransfer.items))
  }

  function handleFolderPick(e: React.ChangeEvent<HTMLInputElement>) {
    resetSelection(Array.from(e.target.files ?? []))
  }

  return (
    <div className="upload-panel">
      <h2 className="h3">Upload sources</h2>

      <label className="label upload-label" htmlFor="upload-week">
        Week
      </label>
      <input
        id="upload-week"
        className="upload-week-input"
        type="number"
        value={week}
        onChange={(e) => setWeek(e.target.value)}
        placeholder="e.g. 5"
      />

      <div
        className={`upload-dropzone${isDragging ? ' upload-dropzone-active' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
      >
        <p className="body-sm">Drag a folder or files here</p>
        <p className="caption">or</p>
        <Button type="button" variant="secondary" onClick={() => folderInputRef.current?.click()}>
          Choose a folder
        </Button>
        <input ref={folderInputRef} type="file" multiple hidden onChange={handleFolderPick} />
      </div>

      {files.length > 0 && (
        <ul className="upload-file-list">
          {supportedFiles.map((f) => (
            <li key={f.webkitRelativePath || f.name} className="caption">
              {f.name}
            </li>
          ))}
          {unsupportedFiles.map((f) => (
            <li key={f.webkitRelativePath || f.name} className="caption upload-file-unsupported">
              {f.name} — not supported ({extensionOf(f.name) || 'no extension'})
            </li>
          ))}
        </ul>
      )}

      <Button
        type="button"
        onClick={() => uploadMutation.mutate()}
        disabled={!weekIsValid || supportedFiles.length === 0 || uploadMutation.isPending}
      >
        {uploadMutation.isPending
          ? 'Uploading…'
          : `Upload ${supportedFiles.length} file${supportedFiles.length === 1 ? '' : 's'}`}
      </Button>
      {uploadMutation.isError && (
        <p className="caption upload-error">{(uploadMutation.error as Error).message}</p>
      )}

      {uploadResults && (
        <ul className="upload-result-list">
          {uploadResults.map((r) => (
            <li key={r.filename} className={`caption upload-result upload-result-${r.status}`}>
              {r.filename} — {RESULT_LABEL[r.status]}
              {r.chunk_count != null && ` (${r.chunk_count} chunks)`}
              {r.error && `: ${r.error}`}
            </li>
          ))}
        </ul>
      )}

      <div className="upload-generate">
        <label className="body-sm upload-force-toggle">
          <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
          Re-generate chunks that already have questions
        </label>
        <p className="caption upload-cost-warning">
          Calls the real Anthropic API — this costs real tokens, one call per chunk.
        </p>
        <Button
          type="button"
          variant="secondary"
          onClick={() => generateMutation.mutate()}
          disabled={!weekIsValid || generateMutation.isPending}
        >
          {generateMutation.isPending
            ? 'Generating…'
            : `Generate questions for week ${week || '…'}`}
        </Button>
        {generateMutation.isError && (
          <p className="caption upload-error">{(generateMutation.error as Error).message}</p>
        )}
        {generateResult && (
          <p className="caption">
            {generateResult.chunks_processed} chunks processed · {generateResult.items_saved} items
            saved · {generateResult.items_rejected} rejected · {generateResult.items_deduped}{' '}
            deduped · {generateResult.chunks_failed} failed
            {generateResult.proposed_topics.length > 0 &&
              ` · proposed topics: ${generateResult.proposed_topics.join(', ')}`}
          </p>
        )}
      </div>
    </div>
  )
}
