import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { useLive } from './live'

/** Load data from the API; returns {data, error, loading, reload}. */
export function useApi(path, { poll, topics } = {}) {
  const { subscribe } = useLive()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const reload = useCallback(async () => {
    if (!path) return
    try {
      setData(await api.get(path))
      setError('')
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [path])
  useEffect(() => {
    setLoading(true)
    reload()
    if (!poll) return
    const t = setInterval(reload, poll)
    return () => clearInterval(t)
  }, [reload, poll])
  const topicKey = (topics || []).join(',')
  useEffect(() => {
    if (!topicKey) return
    const mine = topicKey.split(',')
    let t
    const off = subscribe((changed) => {
      if (changed.includes('*') || mine.some((x) => changed.includes(x))) {
        clearTimeout(t)
        t = setTimeout(reload, 250) // coalesce bursts of events
      }
    })
    return () => { off(); clearTimeout(t) }
  }, [topicKey, reload, subscribe])
  return { data, error, loading, reload }
}

/** Run a mutation, surfacing errors/success in a banner. */
export function useAction(onDone) {
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [busy, setBusy] = useState(false)
  const run = async (fn, message) => {
    setBusy(true)
    setError('')
    setOk('')
    try {
      const r = await fn()
      if (message) setOk(message)
      if (onDone) await onDone(r)
      return r
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }
  const banner = (
    <>
      {error && <div className="error" role="alert">{error}</div>}
      {ok && <div className="notice">{ok}</div>}
    </>
  )
  return { run, busy, error, banner }
}

export const fmtTime = (s) => (s ? new Date(s + 'Z').toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—')
export const fmtDateTime = (s) => (s ? new Date(s + 'Z').toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—')
export const money = (n) => Number(n || 0).toLocaleString(undefined, { style: 'currency', currency: 'USD' })
export const age = (dob) => Math.floor((Date.now() - new Date(dob)) / 31557600000)

export function Badge({ kind = '', children }) {
  return <span className={`badge ${kind}`}>{children}</span>
}

export const statusKind = (s) =>
  ({ completed: 'ok', paid: 'ok', dispensed: 'ok', resulted: 'ok', discharged: 'ok', in_progress: 'info', in_treatment: 'info',
     collected: 'info', admitted: 'info', waiting: 'warn', pending: 'warn', ordered: 'warn', open: 'warn', scheduled: 'info',
     cancelled: 'bad', void: 'bad', no_show: 'bad' }[s] || '')

export function Status({ value }) {
  return <Badge kind={statusKind(value)}>{String(value).replace('_', ' ')}</Badge>
}

export function Field({ label, children }) {
  return (
    <div>
      <label>{label}</label>
      {children}
    </div>
  )
}

export function Modal({ title, onClose, children }) {
  useEffect(() => {
    const h = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="header">
          <h1>{title}</h1>
          <button className="btn ghost sm" onClick={onClose}>Close</button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Table({ cols, rows, empty = 'Nothing here.' }) {
  if (!rows?.length) return <p className="muted">{empty}</p>
  return (
    <table>
      <thead><tr>{cols.map((c) => <th key={c.h}>{c.h}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={r.id ?? i}>{cols.map((c) => <td key={c.h}>{c.render(r)}</td>)}</tr>)}</tbody>
    </table>
  )
}

export function Loading({ state }) {
  if (state.error) return <div className="error">{state.error}</div>
  if (state.loading && !state.data) return <p className="muted">Loading…</p>
  return null
}

// local-time <input type="datetime-local"> <-> naive-UTC ISO used by the API
export const toApiTime = (local) => new Date(local).toISOString().slice(0, 19)
export const nowLocalInput = (plusHours = 0) => {
  const d = new Date(Date.now() + plusHours * 3600000)
  d.setMinutes(0, 0, 0)
  return new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
