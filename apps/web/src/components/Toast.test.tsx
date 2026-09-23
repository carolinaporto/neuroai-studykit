import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from './Toast'
import { useToast } from './toastContext'

function Trigger({ kind, message }: { kind: 'success' | 'error'; message: string }) {
  const toast = useToast()
  useEffect(() => {
    toast[kind](message)
    // Fire once on mount — each test renders a fresh <Trigger>, so there's no need to
    // guard against a second call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return null
}

describe('Toast', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows a success message', () => {
    render(
      <ToastProvider>
        <Trigger kind="success" message="Note created" />
      </ToastProvider>,
    )
    expect(screen.getByText('Note created')).toBeInTheDocument()
  })

  it('shows an error message', () => {
    render(
      <ToastProvider>
        <Trigger kind="error" message="Something went wrong" />
      </ToastProvider>,
    )
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('dismisses itself after the auto-dismiss timeout', () => {
    render(
      <ToastProvider>
        <Trigger kind="success" message="Note created" />
      </ToastProvider>,
    )
    expect(screen.getByText('Note created')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(4000)
    })

    expect(screen.queryByText('Note created')).not.toBeInTheDocument()
  })

  it('dismisses on close-button click', async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    render(
      <ToastProvider>
        <Trigger kind="success" message="Note created" />
      </ToastProvider>,
    )
    expect(screen.getByText('Note created')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /dismiss/i }))

    expect(screen.queryByText('Note created')).not.toBeInTheDocument()
  })
})
