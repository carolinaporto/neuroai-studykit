import { useState } from 'react'

import { useLogin } from '../auth/useAuth'
import { Button } from './Button'
import './SignInPanel.css'

export function SignInPanel({ onClose }: { onClose: () => void }) {
  const [password, setPassword] = useState('')
  const login = useLogin()

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    login.mutate(password, { onSuccess: onClose })
  }

  return (
    <div className="signin-overlay" onClick={onClose}>
      <form className="signin-panel" onClick={(e) => e.stopPropagation()} onSubmit={handleSubmit}>
        <h2 className="h3">Sign in</h2>
        <p className="body-sm signin-hint">Sources, Quizzes and Notes are private.</p>
        <label className="label signin-label" htmlFor="signin-password">
          Password
        </label>
        <input
          id="signin-password"
          type="password"
          className="signin-input"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
        />
        {login.isError && <p className="caption signin-error">{(login.error as Error).message}</p>}
        <div className="signin-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={password.trim() === '' || login.isPending}>
            {login.isPending ? 'Signing in…' : 'Sign in'}
          </Button>
        </div>
      </form>
    </div>
  )
}
