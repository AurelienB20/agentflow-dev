import Editor, { DiffEditor } from '@monaco-editor/react'
import { useEffect, useState } from 'react'
import { EDITOR_OPTIONS } from '../lib/monaco'

function Loading() {
  return <div className="grid h-full place-items-center text-xs text-muted">Loading editor…</div>
}

export function CodeEditor({
  value,
  onChange,
  readOnly,
  height,
}: {
  value: string
  onChange?: (v: string) => void
  readOnly?: boolean
  height: number
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-line" style={{ height }}>
      <Editor
        language="python"
        theme="agentflow"
        value={value}
        onChange={(v) => onChange?.(v ?? '')}
        loading={<Loading />}
        options={{ ...EDITOR_OPTIONS, readOnly, domReadOnly: readOnly }}
      />
    </div>
  )
}

function useNarrow(breakpoint = 640) {
  const [narrow, setNarrow] = useState(() => typeof window !== 'undefined' && window.innerWidth < breakpoint)
  useEffect(() => {
    const onResize = () => setNarrow(window.innerWidth < breakpoint)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [breakpoint])
  return narrow
}

export function CodeDiff({ original, modified, height }: { original: string; modified: string; height: number }) {
  const narrow = useNarrow()
  return (
    <div className="overflow-hidden rounded-xl border border-line" style={{ height }}>
      <DiffEditor
        language="python"
        theme="agentflow"
        original={original}
        modified={modified}
        keepCurrentOriginalModel
        keepCurrentModifiedModel
        loading={<Loading />}
        options={{
          ...EDITOR_OPTIONS,
          readOnly: true,
          renderSideBySide: false,
          useInlineViewWhenSpaceIsLimited: true,
          renderOverviewRuler: false,
          fontSize: narrow ? 11.5 : 12.5,
        }}
      />
    </div>
  )
}

export function CodeView({ code, height }: { code: string; height: number }) {
  return <CodeEditor value={code} readOnly height={height} />
}
