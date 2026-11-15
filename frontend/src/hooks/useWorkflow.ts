import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { RECORDINGS } from '../data/scenarios'
import { api, ApiError, subscribe } from '../services/api'
import { playRecording } from '../services/demoPlayer'
import type { HealthInfo, Scenario } from '../types'
import { initialRunState, reducer } from './workflowReducer'

export type BackendStatus =
  | { state: 'checking' }
  | { state: 'offline' }
  | { state: 'online'; health: HealthInfo }

export function useBackendStatus(): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>({ state: 'checking' })
  useEffect(() => {
    let alive = true
    api
      .health()
      .then((health) => alive && setStatus({ state: 'online', health }))
      .catch(() => alive && setStatus({ state: 'offline' }))
    return () => {
      alive = false
    }
  }, [])
  return status
}

export function useWorkflow() {
  const [run, dispatch] = useReducer(reducer, undefined, initialRunState)
  const stopRef = useRef<(() => void) | null>(null)
  const speedRef = useRef(1)
  const [speed, setSpeedState] = useState(1)

  const stop = () => {
    stopRef.current?.()
    stopRef.current = null
  }
  useEffect(() => stop, [])

  const setSpeed = useCallback((v: number) => {
    speedRef.current = v
    setSpeedState(v)
  }, [])

  const launchDemo = useCallback((scenario: Scenario) => {
    stop()
    dispatch({ type: 'start', mode: 'demo' })
    const rec = RECORDINGS[scenario.id]
    stopRef.current = playRecording(rec.events, (event) => dispatch({ type: 'event', event }), () => speedRef.current)
  }, [])

  const launchLive = useCallback(async (scenario: Scenario, code: string, request: string) => {
    stop()
    dispatch({ type: 'start', mode: 'live' })
    try {
      // Unchanged request: the mission type is known, so the backend skips the
      // classification call. Edited request: let the orchestrator classify it.
      const created = await api.startWorkflow({
        scenario_id: scenario.id,
        task_type: request.trim() === scenario.request.trim() ? scenario.task_type : 'auto',
        code,
        request,
      })
      stopRef.current = subscribe(
        created.events_url,
        (event) => dispatch({ type: 'event', event }),
        (msg) => dispatch({ type: 'error', message: msg }),
      )
    } catch (err) {
      dispatch({ type: 'error', message: err instanceof ApiError ? err.message : 'Could not start the workflow' })
    }
  }, [])

  const cancel = useCallback(async () => {
    if (run.mode === 'live' && run.workflowId && run.phase === 'running') {
      try {
        await api.cancel(run.workflowId)
      } catch {
        stop()
        dispatch({ type: 'error', message: 'Cancel request failed; stream closed.' })
      }
      return
    }
    stop()
    dispatch({
      type: 'event',
      event: {
        seq: run.eventCount + 1,
        workflow_id: run.workflowId ?? 'demo',
        type: 'workflow_cancelled',
        agent: 'orchestrator',
        t: run.elapsed,
        timestamp: new Date().toISOString(),
        data: { reason: 'Replay stopped' },
      },
    })
  }, [run.mode, run.workflowId, run.phase, run.eventCount, run.elapsed])

  const reset = useCallback(() => {
    stop()
    dispatch({ type: 'reset' })
  }, [])

  return { run, launchDemo, launchLive, cancel, reset, speed, setSpeed }
}
