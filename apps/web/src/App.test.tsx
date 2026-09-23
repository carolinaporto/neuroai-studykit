import { ClerkProvider } from '@clerk/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import App from './App'

// A well-formed-but-fake key: Layout -> useSession -> Clerk's useAuth() needs a
// <ClerkProvider>, but this test never signs in or reaches Clerk's network at all, so the
// key only has to pass Clerk's own client-side format check, never a real instance.
const FAKE_CLERK_PUBLISHABLE_KEY = 'pk_test_dGVzdC5jbGVyay5hY2NvdW50cy5kZXYk'

function renderApp() {
  const queryClient = new QueryClient()
  return render(
    <ClerkProvider publishableKey={FAKE_CLERK_PUBLISHABLE_KEY}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/']}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>
    </ClerkProvider>,
  )
}

describe('App', () => {
  it('renders the Overview page with the site nav', () => {
    renderApp()
    expect(screen.getByRole('heading', { name: /neuroai study kit/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
    // Locked sections show as disabled nav buttons while signed out.
    expect(screen.getByRole('button', { name: /sources/i })).toBeDisabled()
  })
})
