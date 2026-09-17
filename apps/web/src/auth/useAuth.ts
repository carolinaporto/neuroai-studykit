import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { getSession, login, logout } from '../api/client'

const SESSION_QUERY_KEY = ['session']

export function useSession() {
  return useQuery({ queryKey: SESSION_QUERY_KEY, queryFn: getSession })
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: login,
    onSuccess: (status) => {
      queryClient.setQueryData(SESSION_QUERY_KEY, status)
    },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: logout,
    onSuccess: (status) => {
      queryClient.setQueryData(SESSION_QUERY_KEY, status)
      // Drop every other cached response too — signing out must not leave locked-section
      // data (sources, notes, quiz weeks) sitting around for the next signed-out visitor.
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== SESSION_QUERY_KEY[0],
      })
    },
  })
}
