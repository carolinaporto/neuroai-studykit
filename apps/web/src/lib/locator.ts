import type { Locator } from '../api/types'

function mmss(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60)
  const s = Math.floor(totalSeconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function formatLocator(locator: Locator): string {
  if (locator.page !== undefined) return `página ${locator.page}`
  if (locator.slide !== undefined) return `slide ${locator.slide}`
  if (locator.t0 !== undefined && locator.t1 !== undefined) {
    return `${mmss(locator.t0)}–${mmss(locator.t1)}`
  }
  return JSON.stringify(locator)
}
