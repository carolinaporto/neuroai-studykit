// A tiny bridge: apps/web/src/api/client.ts's request() needs Clerk's session token for
// the Authorization header, but Clerk only exposes getToken() through the useAuth() hook —
// unusable from a plain function like request(). useSession() (./useAuth.ts) keeps this
// module-level reference in sync with the hook's current value on every render; request()
// just reads it. Module-level state, not React state, on purpose — it needs to be readable
// from outside any component.

type TokenGetter = () => Promise<string | null>

let currentGetToken: TokenGetter | null = null

export function setTokenGetter(getToken: TokenGetter | null): void {
  currentGetToken = getToken
}

export async function getAuthToken(): Promise<string | null> {
  if (!currentGetToken) return null
  return currentGetToken()
}
