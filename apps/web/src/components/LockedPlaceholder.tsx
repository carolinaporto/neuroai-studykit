import { LockIcon } from './icons'
import './LockedPlaceholder.css'

export function LockedPlaceholder({ section }: { section: string }) {
  return (
    <div className="locked-placeholder">
      <LockIcon className="locked-placeholder-icon" />
      <p className="body">{section} is private. Sign in from the sidebar to view it.</p>
    </div>
  )
}
