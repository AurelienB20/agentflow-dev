import type { WorkflowEvent } from '../types'

const MAX_GAP_S = 2.5 // compress long silences so the demo stays snappy

/** Replays a recorded event stream with its original relative timing. */
export function playRecording(
  events: WorkflowEvent[],
  onEvent: (e: WorkflowEvent) => void,
  speed: () => number,
): () => void {
  let index = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  let stopped = false

  const step = () => {
    if (stopped || index >= events.length) return
    onEvent(events[index])
    index += 1
    if (index >= events.length) return
    const gap = Math.min(MAX_GAP_S, Math.max(0, events[index].t - events[index - 1].t))
    timer = setTimeout(step, (gap * 1000) / speed())
  }
  timer = setTimeout(step, 150)
  return () => {
    stopped = true
    if (timer) clearTimeout(timer)
  }
}
