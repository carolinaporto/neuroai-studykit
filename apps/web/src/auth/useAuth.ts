import { useAuth as useClerkAuth, useClerk } from '@clerk/react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { getSession } from '../api/client'
import { setTokenGetter } from './clerkTokenStore'

const SESSION_QUERY_KEY = ['session']

// M12: sign-in/out itself happens entirely through Clerk (its own <SignIn/> component and
// useClerk().signOut()) — this hook's job is (1) keeping the module-level token bridge
// (clerkTokenStore.ts) in sync so apps/web/src/api/client.ts can attach the Authorization
// header, and (2) asking the backend which *app* role a verified session maps to, which
// Clerk itself has no notion of. Kept as a useQuery with this exact {signed_in, role?}
// shape so none of the ~8 pages that already call it need to change.
export function useSession() {
  const { getToken, isSignedIn, isLoaded } = useClerkAuth()

  useEffect(() => {
    setTokenGetter(isSignedIn ? getToken : null)
    return () => setTokenGetter(null)
  }, [getToken, isSignedIn])

  return useQuery({
    queryKey: [...SESSION_QUERY_KEY, isSignedIn ?? false],
    queryFn: getSession,
    enabled: isLoaded,
  })
}

export function useLogout() {
  const { signOut } = useClerk()
  const queryClient = useQueryClient()

  return {
    mutate: async () => {
      await signOut()
      // Drop every other cached response too — signing out must not leave locked-section
      // data (sources, notes, quiz weeks) sitting around for the next signed-out visitor.
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== SESSION_QUERY_KEY[0],
      })
    },
  }
}
