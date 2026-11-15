import type { Recording, Scenario } from '../types'
import fixBug from './recordings/fix-bug.json'
import generateTests from './recordings/generate-tests.json'
import codeReview from './recordings/code-review.json'

// Recordings are produced by backend/scripts/record_demos.py: the real
// LangGraph engine, run once and saved event by event.
export const RECORDINGS: Record<string, Recording> = {
  'fix-bug': fixBug as unknown as Recording,
  'generate-tests': generateTests as unknown as Recording,
  'code-review': codeReview as unknown as Recording,
}

export const SCENARIOS: Scenario[] = ['fix-bug', 'generate-tests', 'code-review'].map((id) => RECORDINGS[id].scenario)
