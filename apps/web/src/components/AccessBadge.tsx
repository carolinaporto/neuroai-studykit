import { LockIcon } from './icons'
import './AccessBadge.css'

export function AccessBadge({ isPublic }: { isPublic: boolean }) {
  return (
    <span className={`ab-badge tag ${isPublic ? 'ab-badge-public' : 'ab-badge-private'}`}>
      <LockIcon open={isPublic} strokeWidth={2} />
      {isPublic ? 'Public' : 'Private'}
    </span>
  )
}
