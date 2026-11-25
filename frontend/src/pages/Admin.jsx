import { useState } from 'react'
import { api } from '../api'
import { Badge, Field, Loading, Table, fmtDateTime, useAction, useApi } from '../ui'

const ROLES = ['admin', 'doctor', 'surgeon', 'nurse', 'pharmacist', 'lab_tech', 'billing', 'receptionist']

export default function Admin() {
  const staff = useApi('/staff')
  const log = useApi('/audit?limit=100', { poll: 20000, topics: ['patients', 'admissions', 'roster', 'imaging'] })
  const [f, setF] = useState({ username: '', full_name: '', password: '', role: 'nurse', specialty: '' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const act = useAction(async () => { setF({ username: '', full_name: '', password: '', role: 'nurse', specialty: '' }); await staff.reload(); await log.reload() })
  return (
    <>
      <div className="header"><div><h1>Admin &amp; audit</h1><span className="muted">Staff accounts and the access trail</span></div></div>
      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Add staff member</h2>
        {act.banner}
        <div className="form">
          <Field label="Username"><input value={f.username} onChange={set('username')} /></Field>
          <Field label="Full name"><input value={f.full_name} onChange={set('full_name')} /></Field>
          <Field label="Temporary password (min 8)"><input type="password" value={f.password} onChange={set('password')} /></Field>
          <Field label="Role"><select value={f.role} onChange={set('role')}>{ROLES.map((r) => <option key={r}>{r}</option>)}</select></Field>
          <Field label="Specialty"><input value={f.specialty} onChange={set('specialty')} /></Field>
          <button className="btn" disabled={act.busy || f.username.length < 3 || !f.full_name.trim() || f.password.length < 8}
            onClick={() => act.run(() => api.post('/staff', { ...f, specialty: f.specialty || null }), 'Staff member created')}>Create</button>
        </div>
      </div>
      <div className="grid cols-2">
        <div className="card">
          <h2>Staff</h2>
          <Loading state={staff} />
          <Table rows={staff.data} cols={[{ h: 'Name', render: (s) => s.full_name }, { h: 'Username', render: (s) => s.username }, { h: 'Role', render: (s) => <Badge>{s.role}</Badge> }, { h: 'Specialty', render: (s) => s.specialty || '—' }]} />
        </div>
        <div className="card">
          <h2>Recent activity</h2>
          <Loading state={log} />
          <Table rows={log.data} cols={[{ h: 'When', render: (l) => fmtDateTime(l.at) }, { h: 'User', render: (l) => l.username }, { h: 'Action', render: (l) => <Badge kind={l.action === 'WARN' ? 'bad' : ''}>{l.action}</Badge> }, { h: 'Entity', render: (l) => `${l.entity}${l.entity_id ? ' #' + l.entity_id : ''}` }, { h: 'Detail', render: (l) => l.detail || '' }]} />
        </div>
      </div>
    </>
  )
}
