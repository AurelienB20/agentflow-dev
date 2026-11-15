import { describe, expect, it } from 'vitest'
import { RECORDINGS } from '../data/scenarios'
import { applyEvent, initialRunState, type RunState } from '../hooks/workflowReducer'

function replay(id: string): RunState {
  return RECORDINGS[id].events.reduce(applyEvent, { ...initialRunState(), phase: 'running', mode: 'demo' })
}

describe('recorded workflows replayed through the UI reducer', () => {
  it('fix-bug shows the correction loop and the corrected code', () => {
    const s = replay('fix-bug')
    expect(s.phase).toBe('completed')
    expect(s.final?.status).toBe('completed')
    expect(s.iteration).toBe(1)
    expect(s.agents.developer.runs).toBe(2)
    expect(s.edges['tester->developer']?.kind).toBe('retry')
    expect(s.final?.final_code).toContain('list(numbers)')
    expect(s.final?.test_results?.executed).toBe(false)
  })

  it('generate-tests shows the quality bar sending work back', () => {
    const s = replay('generate-tests')
    expect(s.qualityScores).toEqual([7.2, 8.8])
    expect(s.qualityThreshold).toBe(8)
    expect(s.agents.reviewer.history.map((h) => h.outcome)).toEqual(['below_threshold', 'approved'])
  })

  it('generate-tests skips the developer', () => {
    const s = replay('generate-tests')
    expect(s.agents.developer.status).toBe('skipped')
    expect(s.agents.developer.runs).toBe(0)
    expect(s.edges['reviewer->tester']?.kind).toBe('retry')
  })

  it('code-review fans out in parallel and joins into the reviewer', () => {
    const s = replay('code-review')
    expect(s.edges['orchestrator->analyzer']?.kind).toBe('parallel')
    expect(s.edges['orchestrator->tester']?.kind).toBe('parallel')
    expect(s.edges['analyzer->reviewer']?.kind).toBe('join')
    expect(s.parallel).toEqual([])
    expect(s.log.some((l) => l.title.startsWith('Results aggregated'))).toBe(true)
  })

  it('every message carries sender, receiver, type and content', () => {
    for (const id of Object.keys(RECORDINGS)) {
      const s = replay(id)
      expect(s.messages.length).toBeGreaterThan(0)
      for (const m of s.messages) {
        expect(m.sender && m.receiver && m.type && m.content).toBeTruthy()
      }
    }
  })

  it('a failed agent turns red, a decision clears active edges', () => {
    let s: RunState = { ...initialRunState(), phase: 'running' }
    s = applyEvent(s, { seq: 1, workflow_id: 'w', type: 'transition', agent: 'orchestrator', t: 0, timestamp: '', data: { source: 'orchestrator', target: 'analyzer', kind: 'dispatch', label: '' } })
    expect(s.edges['orchestrator->analyzer'].active).toBe(true)
    s = applyEvent(s, { seq: 2, workflow_id: 'w', type: 'agent_error', agent: 'analyzer', t: 1, timestamp: '', data: { error: 'timeout', duration_ms: 10 } })
    expect(s.agents.analyzer.status).toBe('failed')
    s = applyEvent(s, { seq: 3, workflow_id: 'w', type: 'decision', agent: 'orchestrator', t: 1, timestamp: '', data: { decision: 'Retry', reason: 'x', kind: 'retry_error', next: ['analyzer'] } })
    expect(s.edges['orchestrator->analyzer'].active).toBe(false)
  })
})
