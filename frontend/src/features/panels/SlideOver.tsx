import { useEffect, useState, type ReactNode } from 'react'

interface Props {
  title: string
  onClose: () => void
  wide?: boolean
  children: ReactNode
}

export function SlideOver({ title, onClose, wide, children }: Props) {
  const [shown, setShown] = useState(false)

  useEffect(() => {
    const frame = requestAnimationFrame(() => setShown(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <button
        type="button"
        aria-label="Close"
        className={`absolute inset-0 bg-[var(--color-ink)]/20 transition-opacity duration-200 ${shown ? 'opacity-100' : 'opacity-0'}`}
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`relative flex h-full w-full flex-col border-l border-[var(--color-line)] bg-[var(--color-paper)] shadow-[-12px_0_40px_-20px_rgba(42,77,60,0.25)] transition-transform duration-200 ease-out ${wide ? 'max-w-xl' : 'max-w-md'} ${shown ? 'translate-x-0' : 'translate-x-full'}`}
      >
        <header className="flex shrink-0 items-center gap-3 border-b border-[var(--color-line)] bg-[var(--color-moss-soft)]/30 px-5 py-4">
          <h2 className="min-w-0 flex-1 font-[family-name:var(--font-display)] text-2xl tracking-tight text-[var(--color-ink)]">
            {title}
          </h2>
          <button type="button" className="btn-ghost text-sm" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</div>
      </aside>
    </div>
  )
}
