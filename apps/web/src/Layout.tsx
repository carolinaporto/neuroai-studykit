import { useState } from 'react'
import { Outlet } from 'react-router-dom'

import { useLogout, useSession } from './auth/useAuth'
import { SignInPanel } from './components/SignInPanel'
import { SiteNav } from './components/SiteNav'
import './Layout.css'

export function Layout() {
  const { data: session } = useSession()
  const logout = useLogout()
  const [showSignIn, setShowSignIn] = useState(false)

  const signedIn = session?.signed_in ?? false

  return (
    <div className="app-shell">
      <SiteNav
        signedIn={signedIn}
        onSignInClick={() => setShowSignIn(true)}
        onSignOutClick={() => logout.mutate()}
      />
      <main className="app-content">
        <Outlet />
      </main>
      {showSignIn && <SignInPanel onClose={() => setShowSignIn(false)} />}
    </div>
  )
}
