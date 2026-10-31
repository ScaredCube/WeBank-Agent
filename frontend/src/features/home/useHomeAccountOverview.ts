import { useEffect, useState } from 'react'

import { api, type BankDashboardData } from '@/lib/api'

export type HomeOverview = {
  status: 'loading' | 'ready' | 'error'
  data: BankDashboardData | null
}

type Result = HomeOverview & {
  token: string
  userId: number
  revision: number
}

/**
 * Account data belongs to the authenticated page; presentation stays pure.
 * In-flight responses from outdated identities or revisions are ignored.
 */
export function useHomeAccountOverview(
  token: string | null,
  userId: number | undefined,
  enabled: boolean,
  revision: number,
): HomeOverview {
  const [result, setResult] = useState<Result | null>(null)

  useEffect(() => {
    if (!enabled || !token || userId == null) return
    let current = true

    void api.bankDashboard(token).then(
      (data) => {
        if (current) setResult({ token, userId, revision, status: 'ready', data })
      },
      () => {
        if (current) setResult({ token, userId, revision, status: 'error', data: null })
      },
    )
    return () => { current = false }
  }, [enabled, token, userId, revision])

  if (!enabled || !token || userId == null ||
      !result || result.token !== token ||
      result.userId !== userId || result.revision !== revision) {
    return { status: 'loading', data: null }
  }

  return { status: result.status, data: result.data }
}
