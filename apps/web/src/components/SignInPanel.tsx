import { SignIn, SignUp } from '@clerk/react'
import { useEffect, useState } from 'react'

import { useSession } from '../auth/useAuth'
import './SignInPanel.css'

// M12: Clerk owns the whole sign-in flow (including the magic-link "check your email, then
// come back here" step — routing="hash" keeps every sub-step inside this overlay via a URL
// hash fragment, no real page navigation or extra routes to configure). This panel's only
// job is the overlay chrome, switching between sign-in and sign-up (Clerk's <SignIn/>
// rejects an email with no existing Clerk account yet — "Couldn't find your account" is
// expected for anyone's very first visit, not an error), and closing itself once the
// session actually goes through.
export function SignInPanel({ onClose }: { onClose: () => void }) {
  const { data: session } = useSession()
  const [mode, setMode] = useState<'sign-in' | 'sign-up'>('sign-in')

  useEffect(() => {
    if (session?.signed_in) onClose()
  }, [session?.signed_in, onClose])

  return (
    <div className="signin-overlay" onClick={onClose}>
      <div className="signin-panel" onClick={(e) => e.stopPropagation()}>
        <div className="signin-panel-inner">
          {mode === 'sign-in' ? <SignIn routing="hash" /> : <SignUp routing="hash" />}
          <button
            type="button"
            className="signin-mode-toggle"
            onClick={() => setMode(mode === 'sign-in' ? 'sign-up' : 'sign-in')}
          >
            {mode === 'sign-in'
              ? 'First time here? Create an account'
              : 'Already have an account? Sign in'}
          </button>
        </div>
      </div>
    </div>
  )
}
