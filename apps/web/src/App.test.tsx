import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import App from './App'

describe('App', () => {
  it('renders the M0 placeholder heading', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: /neuroai study kit — m0/i })).toBeInTheDocument()
  })
})
