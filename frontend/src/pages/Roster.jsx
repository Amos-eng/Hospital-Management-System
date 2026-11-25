import { useState } from 'react'
import { api } from '../api'
import { Badge, Field, Loading, Table, fmtTime, nowLocalInput, toApiTime, useAction, useApi } from '../ui'

const localDay = (iso) => new Date(iso + 'Z').toLocaleDateString('en-CA')
const addDays = (ymd, n) => { const d = new Date(ymd + 'T00:00:00'); d.setDate(d.getDate() + n); return d.toLocaleDateString('en-CA') }
const mondayOf = (d = new Date()) => { const x = new Date(d); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x.toLocaleDateString('en-CA') }
const ROSTERABLE = ['doctor', 'surgeon', 'nurse', 'radiologist', 'pharmacist', 'lab_tech']
const ORDER = ['surgeon', 'doctor', 'nurse', 'radiologist', 'pharmacist', 'lab_tech']

export default function Roster({ user }) {
  const [start, setStart] = useState(mondayOf())
  const canManage = ['doctor', 'admin'].includes(user.role)
  const canCover = ['doctor', 'surgeon', 'nurse', 'admin'].includes(user.role)
  const shifts = useApi(`/shifts?start=${start}&days=7`, { topics: ['roster'] })
  const cover = useApi(canCover ? `/shifts/coverage?start=${start}&days=7` : null, { topics: ['roster'] })
  const duty = useApi('/shifts/on-duty', { topics: ['roster'], poll: 60000 })
  const staff = useApi('/staff')
  const act = useAction(async () => { await Promise.all([shifts.reload(), cover.reload(), duty.reload()]) })
  const days = Array.from({ length: 7 }, (_, i) => addDays(start, i))

  // one row per person
  const people = {}
  ;(shifts.data || []).forEach((s) => { (people[s.user_id] ||= { name: s.user_name, role: s.role, specialty: s.specialty, byDay: {} }); (people[s.user_id].byDay[localDay(s.start)] ||= []).push(s) })
  const rows = Object.entries(people).map(([id, p]) => ({ id, ...p })).sort((a, b) => ORDER.indexOf(a.role) - ORDER.indexOf(b.role) || a.name.localeCompare(b.name))
  const covByDay = {}
  ;(cover.data || []).forEach((c) => { (covByDay[c.date] ||= {})[c.kind] = c })

  return (
    <>
      <div className="header">
        <div><h1>Staff roster</h1><span className="muted">Overlaps and short rests are blocked; understaffed shifts are flagged</span></div>
        <div className="row">
          <button className="btn ghost sm" onClick={() => setStart(addDays(start, -7))}>← Prev</button>
          <button className="btn ghost sm" onClick={() => setStart(mondayOf())}>This week</button>
          <button className="btn ghost sm" onClick={() => setStart(addDays(start, 7))}>Next →</button>
        </div>
      </div>
      {act.banner}
      <div className="grid cols-2" style={{ marginBottom: 14 }}>
        <div className="card">
          <h2>On duty now</h2>
          <Loading state={duty} />
          <Table empty="Nobody is rostered right now." rows={(duty.data || []).filter((s) => s.kind !== 'on_call')} cols={[
            { h: 'Name', render: (s) => s.user_name }, { h: 'Role', render: (s) => <Badge>{s.role.replace('_', ' ')}</Badge> }, { h: 'Unit', render: (s) => s.unit }, { h: 'Until', render: (s) => fmtTime(s.end) }]} />
          {(duty.data || []).some((s) => s.kind === 'on_call') && <p className="small muted" style={{ marginTop: 8 }}>On call: {(duty.data || []).filter((s) => s.kind === 'on_call').map((s) => s.user_name).join(', ')}</p>}
        </div>
        {canManage && <AddShift staff={(staff.data || []).filter((s) => ROSTERABLE.includes(s.role))} act={act} />}
      </div>

      <div className="card roster">
        <Loading state={shifts} />
        <table>
          <thead>
            <tr><th>Staff</th>{days.map((d) => <th key={d}>{new Date(d + 'T00:00:00').toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' })}</th>)}</tr>
            {canCover && (
              <tr><td className="muted small">Coverage (min: 2 nurses, 1 doctor, 1 surgeon)</td>
                {days.map((d) => (
                  <td key={d}>
                    {['day', 'night'].map((k) => {
                      const c = covByDay[d]?.[k]
                      if (!c) return null
                      const gap = Object.entries(c.gaps).map(([r, n]) => `${n} ${r}${n > 1 ? 's' : ''}`).join(', ')
                      return <div key={k} className={`cov ${c.understaffed ? 'gap' : 'ok'}`} title={c.understaffed ? `Need ${gap}` : 'Fully covered'}>{k}: {c.understaffed ? `short ${gap}` : 'covered'}</div>
                    })}
                  </td>
                ))}
              </tr>
            )}
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={8} className="muted">No shifts this week.</td></tr>}
            {rows.map((p) => (
              <tr key={p.id}>
                <td><b>{p.name}</b><br /><span className="muted small">{p.specialty || p.role}</span></td>
                {days.map((d) => (
                  <td key={d}>
                    {(p.byDay[d] || []).map((s) => (
                      <span key={s.id} className={`chip ${s.kind} ${canManage ? 'can-delete' : ''}`} title={canManage ? 'Click to remove' : `${s.unit}${s.notes ? ' · ' + s.notes : ''}`}
                        role={canManage ? 'button' : undefined}
                        onClick={() => canManage && window.confirm(`Remove ${p.name}'s ${s.kind} shift?`) && act.run(() => api.del(`/shifts/${s.id}`), 'Shift removed')}>
                        {s.kind === 'on_call' ? 'on call' : s.kind} · {fmtTime(s.start)}–{fmtTime(s.end)}<br />{s.unit}
                      </span>
                    ))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

const PRESETS = { day: ['07:00', 12], night: ['19:00', 12], on_call: ['19:00', 12] }

function AddShift({ staff, act }) {
  const [f, setF] = useState({ user_id: '', kind: 'day', unit: 'General', date: new Date().toLocaleDateString('en-CA'), notes: '' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const [hhmm, hours] = PRESETS[f.kind]
  const startLocal = `${f.date}T${hhmm}`
  const end = new Date(new Date(startLocal).getTime() + hours * 3600000)
  return (
    <div className="card">
      <h2>Add shift</h2>
      <div className="form">
        <Field label="Staff member">
          <select value={f.user_id} onChange={set('user_id')}>
            <option value="">Select…</option>
            {staff.map((s) => <option key={s.id} value={s.id}>{s.full_name} · {s.role.replace('_', ' ')}</option>)}
          </select>
        </Field>
        <Field label="Date"><input type="date" value={f.date} onChange={set('date')} /></Field>
        <Field label="Shift"><select value={f.kind} onChange={set('kind')}><option value="day">Day 07:00–19:00</option><option value="night">Night 19:00–07:00</option><option value="on_call">On call 19:00–07:00</option></select></Field>
        <Field label="Unit"><select value={f.unit} onChange={set('unit')}>{['General', 'ER', 'ICU', 'OR', 'Surgery', 'Pediatrics', 'Radiology', 'Pharmacy', 'Lab'].map((u) => <option key={u}>{u}</option>)}</select></Field>
        <button className="btn" disabled={act.busy || !f.user_id || !f.date}
          onClick={() => act.run(() => api.post('/shifts', { user_id: +f.user_id, kind: f.kind, unit: f.unit, notes: f.notes || null, start: toApiTime(startLocal), end: end.toISOString().slice(0, 19) }), 'Shift added')}>Add</button>
      </div>
    </div>
  )
}
