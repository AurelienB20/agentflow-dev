// Bundle Monaco locally (no CDN at runtime) with only the editor worker and Python.
import { loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor/editor/editor.api'
import 'monaco-editor/languages/definitions/python/register'
import 'monaco-codicon.css'
import EditorWorker from 'monaco-editor/editor/editor.worker?worker&inline'

declare global {
  interface Window {
    MonacoEnvironment?: { getWorker: (workerId: string, label: string) => Worker }
  }
}

window.MonacoEnvironment = { getWorker: () => new EditorWorker() }

monaco.editor.defineTheme('agentflow', {
  base: 'vs-dark',
  inherit: true,
  rules: [
    { token: 'comment', foreground: '6b7394', fontStyle: 'italic' },
    { token: 'keyword', foreground: 'a5b4fc' },
    { token: 'string', foreground: '67e8f9' },
    { token: 'number', foreground: 'fbbf24' },
  ],
  colors: {
    'editor.background': '#0e1428',
    'editor.lineHighlightBackground': '#151c30',
    'editorLineNumber.foreground': '#3b4566',
    'editorLineNumber.activeForeground': '#8b93b0',
    'editorGutter.background': '#0e1428',
    'editor.selectionBackground': '#6366f155',
    'diffEditor.insertedTextBackground': '#22c55e22',
    'diffEditor.removedTextBackground': '#ef444422',
    'diffEditor.insertedLineBackground': '#22c55e14',
    'diffEditor.removedLineBackground': '#ef444414',
  },
})

loader.config({ monaco })

export const EDITOR_OPTIONS = {
  minimap: { enabled: false },
  fontSize: 12.5,
  fontFamily: "'JetBrains Mono', ui-monospace, monospace",
  lineNumbersMinChars: 3,
  scrollBeyondLastLine: false,
  renderLineHighlight: 'line' as const,
  padding: { top: 10, bottom: 10 },
  overviewRulerLanes: 0,
  scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8, alwaysConsumeMouseWheel: false },
  automaticLayout: true,
  tabSize: 4,
}
