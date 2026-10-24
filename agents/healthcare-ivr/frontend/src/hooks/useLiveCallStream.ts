import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { api } from '../api/client'
import { callKeys, liveCallKeys } from '../api/queries'

export type LiveActivity = 'caller_speaking' | 'agent_thinking' | 'agent_speaking' | 'listening'

type StreamMessage =
  | { kind: 'subscribed' }
  | { kind: 'activity'; activity: LiveActivity }
  | { kind: 'turn' | 'event' }
  | { kind: 'ended' }

/**
 * Follows a live call over server-sent events. New turns and events refresh the call's data;
 * activity messages say who is talking right now. Returns null when the call isn't live.
 */
export function useLiveCallStream(callId: string, enabled: boolean): LiveActivity | null {
  const queryClient = useQueryClient()
  const [activity, setActivity] = useState<LiveActivity | null>(null)

  useEffect(() => {
    if (!enabled) return
    const source = new EventSource(api.callStreamUrl(callId))
    const refresh = () => {
      void queryClient.invalidateQueries({ queryKey: callKeys.detail(callId) })
      void queryClient.invalidateQueries({ queryKey: liveCallKeys.all })
    }
    source.onmessage = (message: MessageEvent<string>) => {
      const update = JSON.parse(message.data) as StreamMessage
      switch (update.kind) {
        case 'activity':
          setActivity(update.activity)
          break
        case 'turn':
        case 'event':
          refresh()
          break
        case 'ended':
          setActivity(null)
          refresh()
          source.close()
          break
      }
    }
    return () => source.close()
  }, [callId, enabled, queryClient])

  return enabled ? activity : null
}
