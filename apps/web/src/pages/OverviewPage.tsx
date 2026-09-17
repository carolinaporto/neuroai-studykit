import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { useSession } from '../auth/useAuth'
import { AccessBadge } from '../components/AccessBadge'
import {
  CheckTargetIcon,
  HomeworkIcon,
  LockIcon,
  NotesIcon,
  SourcesIcon,
} from '../components/icons'
import './OverviewPage.css'

interface Section {
  label: string
  description: string
  path: string
  Icon: (props: { className?: string }) => ReactNode
  isPublic: boolean
}

const SECTIONS: Section[] = [
  {
    label: 'Sources',
    description:
      'Class PDFs, slides and transcripts, grouped by week — what every quiz question is anchored to.',
    path: '/sources',
    Icon: SourcesIcon,
    isPublic: false,
  },
  {
    label: 'Quizzes',
    description:
      'Weekly recall checks generated from your own material, graded against a rubric, not vibes.',
    path: '/quizzes',
    Icon: CheckTargetIcon,
    isPublic: false,
  },
  {
    label: 'Notes & Insights',
    description: 'Short notes and links to your own documents, tagged by discipline.',
    path: '/notes',
    Icon: NotesIcon,
    isPublic: false,
  },
  {
    label: 'Homework',
    description: 'The public research portfolio for the semester — write-ups, pages and projects.',
    path: '/homework',
    Icon: HomeworkIcon,
    isPublic: true,
  },
]

export function OverviewPage() {
  const { data: session } = useSession()
  const signedIn = session?.signed_in ?? false

  return (
    <div className="page overview">
      <h1 className="display">NeuroAI Study Kit</h1>
      <p className="body overview-lede">
        A personal practice-testing site for Foundations of Neuro AI — weekly recall quizzes, class
        sources, insight notes, and the public research homework portfolio for the semester.
      </p>

      <div className="overview-grid">
        {SECTIONS.map(({ label, description, path, Icon, isPublic }) => {
          const locked = !isPublic && !signedIn
          const content = (
            <>
              <div className="overview-card-top">
                <Icon className="overview-card-icon" />
                <AccessBadge isPublic={isPublic} />
              </div>
              <p className="h3 overview-card-title">{label}</p>
              <p className="body-sm overview-card-desc">{description}</p>
              {locked && (
                <p className="caption overview-card-locked-note">
                  <LockIcon className="overview-card-lock-icon" />
                  Sign in to view
                </p>
              )}
            </>
          )
          return locked ? (
            <div key={path} className="overview-card overview-card-is-locked">
              {content}
            </div>
          ) : (
            <Link key={path} to={path} className="overview-card">
              {content}
            </Link>
          )
        })}
      </div>
    </div>
  )
}
