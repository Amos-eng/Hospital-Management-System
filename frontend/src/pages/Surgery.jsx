import { useState } from 'react'
import { api } from '../api'
import { Field, Loading, Modal, Status, Table, nowLocalInput, toApiTime, tzOffset, useAction, useApi } from '../ui'

const START_H = 6
const SPAN_H = 14 // 06:00 – 20:00

function hoursOf(iso) {
  const d = new Date(iso + 'Z')
  return d.getHours() + d.getMinutes() / 60
}

export default function Surgery({ user }) {
  const [day, setDay] = useState(() => new Date().toLocaleDateString('en-CA'))
  const rooms = useApi('/operating-rooms')
  const list = useApi(`/surgeries?day=${day}&tz_offset=${tzOffset()}`, { poll: 60000, topics: ['surgery'] })
  const [open, setOpen] = useState(false)
  const [sel, setSel] = useState(null)
  const [warn, setWarn] = useState([])
  const act = useAction(list.reload)
  const canEdit = ['doctor', 'surgeon', 'nurse', 'admin'].includes(user.role)

  // the API filters by UTC day; for the timeline, show only cases that start on the chosen local day
  const cases = (list.data || [])
  const hours = Array.from({ length: SPAN_H }, (_, i) => `${String(START_H + i).padStart(2, '0')}`)

  return (
    <>
      <div className="header">
        <div><h1>Surgery &amp; OR board</h1><span className="muted">Room, surgeon and team conflicts are checked on booking</span></div>
        <div className="row">
          <input type="date" value={day} onChange={(e) => setDay(e.target.value)} style={{ width: 160 }} />
          {canEdit && <button className="btn" onClick={() => setOpen(true)}>+ Schedule surgery</button>}
        </div>
      </div>
      {act.banner}
      {warn.length > 0 && <div className="error" role="alert" style={{ borderColor: 'var(--warn)', color: '#ffe1a0', background: 'rgba(255,183,3,.1)' }}><b>Surgery booked, but check the roster:</b><ul style={{ margin: '6px 0 0' }}>{warn.map((w) => <li key={w}>{w}</li>)}</ul><button className="btn ghost sm" style={{ marginTop: 8 }} onClick={() => setWarn([])}>Dismiss</button></div>}
      <Loading state={list} />
      <div className="card or-board">
        <div className="or-hours"><div /><div className="hrs">{hours.map((h) => <span key={h}>{h}:00</span>)}</div></div>
        {(rooms.data || []).map((r) => (
          <div className="or-row" key={r.id}>
            <div className="or-name">{r.name}</div>
            <div className="or-track">
              {cases.filter((c) => c.room_id === r.id).map((c) => {
                const s = Math.max(hoursOf(c.start), START_H)
                const e = Math.min(hoursOf(c.end) || 24, START_H + SPAN_H)
                if (e <= s) return null
                return (
                  <div key={c.id} className={`case ${c.priority} ${c.status}`} role="button" tabIndex={0} onClick={() => setSel(c)}
                    style={{ left: `${((s - START_H) / SPAN_H) * 100}%`, width: `${((e - s) / SPAN_H) * 100}%` }}
                    title={`${c.procedure} — ${c.surgeon_name}`}>
                    <b>{c.procedure}</b><br />{c.patient_name} · {c.surgeon_name}
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>
      <div className="card" style={{ marginTop: 14 }}>
        <h2>Cases</h2>
        <Table empty="No surgeries scheduled for this day." rows={cases} cols={[
          { h: 'Room', render: (c) => c.room_name },
          { h: 'Procedure', render: (c) => <><b>{c.procedure}</b><br /><span className="muted small">{c.patient_name}</span></> },
          { h: 'Surgeon', render: (c) => c.surgeon_name },
          { h: 'Team', render: (c) => c.team.map((t) => `${t.name} (${t.role.replace('_', ' ')})`).join(', ') || '—' },
          { h: 'Priority', render: (c) => <span className={`badge ${c.priority === 'emergency' ? 'bad' : c.priority === 'urgent' ? 'warn' : ''}`}>{c.priority}</span> },
          { h: 'Status', render: (c) => <Status value={c.status} /> },
        ]} />
      </div>
      {open && <Schedule rooms={rooms.data || []} onClose={() => setOpen(false)} onDone={async (r) => { setOpen(false); setWarn(r?.warnings || []); await list.reload() }} />}
      {sel && <CaseModal c={sel} canEdit={canEdit} onClose={() => setSel(null)} onDone={async () => { setSel(null); await list.reload() }} />}
    </>
  )
}

function CaseModal({ c, canEdit, onClose, onDone }) {
  const act = useAction(onDone)
  const set = (status) => act.run(() => api.patch(`/surgeries/${c.id}/status`, { status }))
  return (
    <Modal title={c.procedure} onClose={onClose}>
      {act.banner}
      <p><b>{c.patient_name}</b> · {c.room_name} · {c.surgeon_name} · <Status value={c.status} /></p>
      {c.notes && <p className="muted">{c.notes}</p>}
      {canEdit && (
        <div className="row">
          {c.status === 'scheduled' && <button className="btn" disabled={act.busy} onClick={() => set('in_progress')}>Start surgery</button>}
          {c.status === 'in_progress' && <button className="btn" disabled={act.busy} onClick={() => set('completed')}>Mark completed</button>}
          {['scheduled', 'in_progress'].includes(c.status) && <button className="btn danger" disabled={act.busy} onClick={() => set('cancelled')}>Cancel</button>}
        </div>
      )}
    </Modal>
  )
}

function Schedule({ rooms, onClose, onDone }) {
  const patients = useApi('/patients?limit=200')
  const staff = useApi('/staff')
  const [f, setF] = useState({ patient_id: '', room_id: '', surgeon_id: '', procedure: '', priority: 'elective', start: nowLocalInput(1), end: nowLocalInput(3), notes: '', anesth: '', scrub: '' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const act = useAction(onDone)
  const surgeons = (staff.data || []).filter((s) => s.role === 'surgeon')
  const team = []
  if (f.anesth) team.push({ user_id: +f.anesth, role: 'anesthesiologist' })
  if (f.scrub) team.push({ user_id: +f.scrub, role: 'scrub_nurse' })
  const ready = f.patient_id && f.room_id && f.surgeon_id && f.procedure.trim() && f.start < f.end
  return (
    <Modal title="Schedule surgery" onClose={onClose}>
      {act.banner}
      <div className="form">
        <Field label="Patient"><select value={f.patient_id} onChange={set('patient_id')}><option value="">Select…</option>{(patients.data || []).map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name} · {p.mrn}</option>)}</select></Field>
        <Field label="Procedure"><input value={f.procedure} onChange={set('procedure')} /></Field>
        <Field label="Operating room"><select value={f.room_id} onChange={set('room_id')}><option value="">Select…</option>{rooms.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></Field>
        <Field label="Lead surgeon"><select value={f.surgeon_id} onChange={set('surgeon_id')}><option value="">Select…</option>{surgeons.map((s) => <option key={s.id} value={s.id}>{s.full_name} · {s.specialty}</option>)}</select></Field>
        <Field label="Start"><input type="datetime-local" value={f.start} onChange={set('start')} /></Field>
        <Field label="End"><input type="datetime-local" value={f.end} onChange={set('end')} /></Field>
        <Field label="Priority"><select value={f.priority} onChange={set('priority')}><option>elective</option><option>urgent</option><option>emergency</option></select></Field>
        <Field label="Anesthesiologist"><select value={f.anesth} onChange={set('anesth')}><option value="">None</option>{(staff.data || []).filter((s) => s.specialty === 'Anesthesiology').map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}</select></Field>
        <Field label="Scrub nurse"><select value={f.scrub} onChange={set('scrub')}><option value="">None</option>{(staff.data || []).filter((s) => s.role === 'nurse').map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}</select></Field>
      </div>
      <div style={{ margin: '12px 0' }}><Field label="Notes"><textarea rows={2} value={f.notes} onChange={set('notes')} /></Field></div>
      <button className="btn" disabled={act.busy || !ready}
        onClick={() => act.run(() => api.post('/surgeries', { patient_id: +f.patient_id, room_id: +f.room_id, surgeon_id: +f.surgeon_id, procedure: f.procedure, priority: f.priority, notes: f.notes || null, start: toApiTime(f.start), end: toApiTime(f.end), team }))}>Book surgery</button>
    </Modal>
  )
}
