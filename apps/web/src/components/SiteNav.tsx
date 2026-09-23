import { NavLink } from 'react-router-dom'

import {
  CheckTargetIcon,
  HomeworkIcon,
  LockIcon,
  NotesIcon,
  OverviewIcon,
  ProgressIcon,
  ReviewIcon,
  SourcesIcon,
} from './icons'
import './SiteNav.css'

function SynapseMark() {
  return (
    <svg className="synav-mark" width="22" height="22" viewBox="0 0 24 24">
      <line x1="6" y1="7" x2="18" y2="17" />
      <line x1="6" y1="17" x2="18" y2="7" />
      <circle cx="6" cy="7" r="2.5" />
      <circle cx="18" cy="7" r="2.5" className="dim" />
      <circle cx="6" cy="17" r="2.5" className="dim" />
      <circle cx="18" cy="17" r="2.5" />
    </svg>
  )
}

interface SiteNavProps {
  signedIn: boolean
  onSignInClick: () => void
  onSignOutClick: () => void
}

const lockedItems = [
  { label: 'Sources', path: '/sources', Icon: SourcesIcon },
  { label: 'Review', path: '/review', Icon: ReviewIcon },
  { label: 'Quizzes', path: '/quizzes', Icon: CheckTargetIcon },
  { label: 'Progress', path: '/progress', Icon: ProgressIcon },
  { label: 'Notes & Insights', path: '/notes', Icon: NotesIcon },
]

export function SiteNav({ signedIn, onSignInClick, onSignOutClick }: SiteNavProps) {
  return (
    <nav className="synav">
      <div className="synav-brand">
        <SynapseMark />
        <span className="synav-name">Synapse</span>
      </div>
      <div className="synav-sub caption">Foundations of Neuro AI</div>

      <ul className="synav-list">
        <li>
          <NavLink
            to="/"
            end
            className={({ isActive }) => `synav-item${isActive ? ' is-active' : ''}`}
          >
            <OverviewIcon className="icon" />
            <span className="label">Overview</span>
          </NavLink>
        </li>
        {lockedItems.map(({ label, path, Icon }) =>
          signedIn ? (
            <li key={path}>
              <NavLink
                to={path}
                className={({ isActive }) => `synav-item${isActive ? ' is-active' : ''}`}
              >
                <Icon className="icon" />
                <span className="label">{label}</span>
              </NavLink>
            </li>
          ) : (
            <li key={path}>
              <button className="synav-item is-locked" disabled>
                <Icon className="icon" />
                <span className="label">{label}</span>
                <LockIcon className="lock" />
              </button>
            </li>
          ),
        )}
        <li>
          {/* Homework never carries .is-active or .is-locked on its own account — always
              the Public tag instead, per design/synapse/components/SiteNav/README.md. */}
          <NavLink to="/homework" className="synav-item">
            <HomeworkIcon className="icon" />
            <span className="label">Homework</span>
            <span className="pub tag">Public</span>
          </NavLink>
        </li>
      </ul>

      <div className="synav-foot">
        <button className="synav-signin button" onClick={signedIn ? onSignOutClick : onSignInClick}>
          {signedIn ? 'Sign out' : 'Sign in'}
        </button>
      </div>
    </nav>
  )
}
