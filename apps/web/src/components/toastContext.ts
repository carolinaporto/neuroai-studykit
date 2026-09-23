import { createContext, useContext } from 'react'

export type ToastVariant = 'success' | 'error'

export interface ToastContextValue {
  success: (message: string) => void
  error: (message: string) => void
}

export const ToastContext = createContext<ToastContextValue | null>(null)

// Throws rather than returning undefined — every call site is inside <ToastProvider> (it
// wraps the whole app in main.tsx), so a missing provider is a real bug, not a state to
// handle gracefully.
export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within a ToastProvider')
  return ctx
}
