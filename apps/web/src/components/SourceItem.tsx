import type { ReactNode } from 'react'

import { DocumentIcon, LockIcon, PlayIcon, SlidesIcon } from './icons'
import './SourceItem.css'

const ICON_BY_KIND: Record<string, (props: { className?: string }) => ReactNode> = {
  slides: SlidesIcon,
  transcript: PlayIcon,
  lecture_pdf: DocumentIcon,
  paper: DocumentIcon,
  notes: DocumentIcon,
}

export function SourceList({ children }: { children: ReactNode }) {
  return <div className="si-wrap">{children}</div>
}

export function SourceItem({ kind, title, meta }: { kind: string; title: string; meta: string }) {
  const IconComp = ICON_BY_KIND[kind] ?? DocumentIcon
  return (
    <div className="si-row">
      <div className="si-icon">
        <IconComp />
      </div>
      <div className="si-body">
        <div className="body si-title">{title}</div>
        <div className="caption si-meta">{meta}</div>
      </div>
      <LockIcon className="si-lock" />
    </div>
  )
}
