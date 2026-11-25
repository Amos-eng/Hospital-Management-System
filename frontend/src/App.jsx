import { useEffect, useState } from 'react'
import { api, getToken, setToken } from './api'
import Dashboard from './pages/Dashboard'
import ER from './pages/ER'
import Surgery from './pages/Surgery'
import Patients from './pages/Patients'
import Appointments from './pages/Appointments'
import Pharmacy from './pages/Pharmacy'
import Labs from './pages/Labs'
import Billing from './pages/Billing'
import Admin from './pages/Admin'
import Wards from './pages/Wards'
import Roster from './pages/Roster'
import Imaging from './pages/Imaging'
import { LiveProvider, useLive } from './live'
import { Field, Modal, useAction } from './ui'

const CLIN = ['doctor', 'surgeon', 'nurse']
const PAGES = [
  { id: 'dashboard', label: 'Dashboard', roles: null, C: Dashboard },
  { id: 'er', label: 'Emergency Room', roles: [...CLIN, 'receptionist'], C: ER },
  { id: 'surgery', label: 'Surgery / OR', roles: CLIN, C: Surgery },
  { id: 'wards', label: 'Inpatient Wards', roles: CLIN, C: Wards },
  { id: 'patients', label: 'Patients', roles: [...CLIN, 'receptionist', 'billing', 'pharmacist', 'lab_tech'], C: Patients },
  { id: 'appointments', label: 'Appointments', roles: [...CLIN, 'receptionist'], C: Appointments },
  { id: 'imaging', label: 'Radiology', roles: ['radiologist', ...CLIN], C: Imaging },
  { id: 'pharmacy', label: 'Pharmacy', roles: ['pharmacist', 'doctor', 'surgeon'], C: Pharmacy },
  { id: 'labs', label: 'Laboratory', roles: ['lab_tech', ...CLIN], C: Labs },
  { id: 'billing', label: 'Billing', roles: ['billing', 'receptionist'], C: Billing },
  { id: 'roster', label: 'Staff Roster', roles: null, C: Roster },
  { id: 'admin', label: 'Admin & Audit', roles: [], C: Admin },
]
const canSee = (page, role) => role === 'admin' || !page.roles || page.roles.includes(role)

const DEMO = ['admin', 'dr.shepherd', 'dr.hunt', 'nurse.olivia', 'dr.chen', 'pharm.lee', 'lab.tran', 'bill.cole', 'front.amy']

function Login({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const r = await api.login(username, password)
      setToken(r.access_token)
      onLogin(r.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <div className="brand">Grace Memorial<small>Hospital Management System</small></div>
        {error && <div className="error">{error}</div>}
        <div className="grid">
          <div><label>Username</label><input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required /></div>
          <div><label>Password</label><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
          <button className="btn" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </div>
        <div className="demo">
          Demo accounts (password <code>Hospital123!</code>):
          <div className="demo-users">
            {DEMO.map((u) => <button type="button" key={u} className="btn ghost sm" onClick={() => { setUsername(u); setPassword('Hospital123!') }}>{u}</button>)}
          </div>
        </div>
      </form>
    </div>
  )
}

function ChangePassword({ onClose }) {
  const [f, setF] = useState({ current: '', next: '', confirm: '' })
  const [done, setDone] = useState(false)
  const act = useAction(async () => setDone(true))
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const mismatch = f.confirm !== '' && f.next !== f.confirm
  return (
    <Modal title="Change password" onClose={onClose}>
      {done ? (
        <><div className="notice">Password changed. Use the new one next time you sign in.</div><button className="btn" onClick={onClose}>Close</button></>
      ) : (
        <>
          {act.banner}
          <div className="grid" style={{ maxWidth: 360 }}>
            <Field label="Current password"><input type="password" autoComplete="current-password" value={f.current} onChange={set('current')} /></Field>
            <Field label="New password (min 8 characters)"><input type="password" autoComplete="new-password" value={f.next} onChange={set('next')} /></Field>
            <Field label="Confirm new password"><input type="password" autoComplete="new-password" value={f.confirm} onChange={set('confirm')} /></Field>
            {mismatch && <span className="small" style={{ color: 'var(--bad)' }}>Passwords do not match</span>}
            <button className="btn" disabled={act.busy || !f.current || f.next.length < 8 || f.next !== f.confirm}
              onClick={() => act.run(() => api.post('/auth/change-password', { current_password: f.current, new_password: f.next }))}>Change password</button>
          </div>
        </>
      )}
    </Modal>
  )
}

function LiveDot() {
  const { status } = useLive()
  return <div className="small muted" style={{ padding: '0 10px 8px' }}><span className={`dot ${status}`} />{status === 'live' ? 'Live updates on' : status === 'connecting' ? 'Connecting…' : 'Offline — retrying'}</div>
}

export default function App() {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(!getToken())
  const [page, setPage] = useState('dashboard')
  const [pwOpen, setPwOpen] = useState(false)

  useEffect(() => {
    if (getToken()) api.get('/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setReady(true))
    const out = () => setUser(null)
    window.addEventListener('hms-logout', out)
    return () => window.removeEventListener('hms-logout', out)
  }, [])

  if (!ready) return <p className="muted" style={{ padding: 24 }}>Loading…</p>
  if (!user) return <Login onLogin={(u) => { setUser(u); setPage('dashboard') }} />

  const visible = PAGES.filter((p) => (p.id === 'admin' ? user.role === 'admin' : canSee(p, user.role)))
  const Current = (visible.find((p) => p.id === page) || visible[0]).C

  return (
    <LiveProvider key={user.id}>
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">Grace Memorial<small>Hospital Management</small></div>
        {visible.map((p) => (
          <button key={p.id} className={`nav ${p.id === page ? 'active' : ''}`} onClick={() => setPage(p.id)}>{p.label}</button>
        ))}
        <div className="spacer" />
        <LiveDot />
        <div className="me">
          <b>{user.full_name}</b><br />
          <span className="muted">{user.role.replace('_', ' ')}{user.specialty ? ` · ${user.specialty}` : ''}</span><br />
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn ghost sm" onClick={() => setPwOpen(true)}>Password</button>
            <button className="btn ghost sm" onClick={() => { setToken(null); setUser(null) }}>Sign out</button>
          </div>
        </div>
      </aside>
      <main className="main"><Current user={user} /></main>
      {pwOpen && <ChangePassword onClose={() => setPwOpen(false)} />}
    </div>
    </LiveProvider>
  )
}
