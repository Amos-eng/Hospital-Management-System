import { useState } from 'react'
import { api } from '../api'
import { Badge, Field, Loading, Modal, Status, Table, age, fmtDateTime, useAction, useApi } from '../ui'

const CLIN = ['doctor', 'surgeon', 'nurse', 'admin']

export default function Patients({ user }) {
  const [q, setQ] = useState('')
  const list = useApi(`/patients?q=${encodeURIComponent(q)}`, { topics: ['patients'] })
  const [sel, setSel] = useState(null)
  const [reg, setReg] = useState(false)
  const canRegister = [...CLIN, 'receptionist'].includes(user.role)
  return (
    <>
      <div className="header">
        <div><h1>Patients</h1><span className="muted">Every chart open is recorded in the audit log</span></div>
        <div className="row">
          <input placeholder="Search name, MRN, phone…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 280 }} />
          {canRegister && <button className="btn" onClick={() => setReg(true)}>+ Register patient</button>}
        </div>
      </div>
      <div className="card">
        <Loading state={list} />
        <Table empty="No patients match." rows={list.data} cols={[
          { h: 'MRN', render: (p) => p.mrn },
          { h: 'Name', render: (p) => <button className="btn ghost sm" onClick={() => setSel(p)}>{p.first_name} {p.last_name}</button> },
          { h: 'Age / sex', render: (p) => `${age(p.dob)} · ${p.sex}` },
          { h: 'Blood', render: (p) => p.blood_type || '—' },
          { h: 'Allergies', render: (p) => (p.allergies ? <Badge kind="bad">{p.allergies}</Badge> : <span className="muted">none known</span>) },
          { h: 'Phone', render: (p) => p.phone || '—' },
        ]} />
      </div>
      {reg && <Register onClose={() => setReg(false)} onDone={async () => { setReg(false); await list.reload() }} />}
      {sel && <Chart patient={sel} user={user} onClose={() => setSel(null)} />}
    </>
  )
}

function Register({ onClose, onDone }) {
  const [f, setF] = useState({ first_name: '', last_name: '', dob: '', sex: 'female', phone: '', blood_type: '', allergies: '', insurance_provider: '', insurance_number: '', emergency_contact: '', address: '' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const act = useAction(onDone)
  const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === '' ? null : v]))
  return (
    <Modal title="Register patient" onClose={onClose}>
      {act.banner}
      <div className="form">
        <Field label="First name"><input value={f.first_name} onChange={set('first_name')} /></Field>
        <Field label="Last name"><input value={f.last_name} onChange={set('last_name')} /></Field>
        <Field label="Date of birth"><input type="date" value={f.dob} onChange={set('dob')} /></Field>
        <Field label="Sex"><select value={f.sex} onChange={set('sex')}><option>female</option><option>male</option><option>other</option></select></Field>
        <Field label="Phone"><input value={f.phone} onChange={set('phone')} /></Field>
        <Field label="Blood type"><select value={f.blood_type} onChange={set('blood_type')}><option value="">Unknown</option>{['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'].map((b) => <option key={b}>{b}</option>)}</select></Field>
        <Field label="Allergies"><input value={f.allergies} onChange={set('allergies')} placeholder="e.g. Penicillin, Latex" /></Field>
        <Field label="Insurance provider"><input value={f.insurance_provider} onChange={set('insurance_provider')} /></Field>
        <Field label="Insurance no."><input value={f.insurance_number} onChange={set('insurance_number')} /></Field>
        <Field label="Emergency contact"><input value={f.emergency_contact} onChange={set('emergency_contact')} /></Field>
        <Field label="Address"><input value={f.address} onChange={set('address')} /></Field>
      </div>
      <p><button className="btn" disabled={act.busy || !f.first_name.trim() || !f.last_name.trim() || !f.dob} onClick={() => act.run(() => api.post('/patients', body))}>Register</button></p>
    </Modal>
  )
}

function Chart({ patient, user, onClose }) {
  const clinician = CLIN.includes(user.role)
  const [tab, setTab] = useState(clinician ? 'notes' : 'info')
  const tabs = clinician ? ['notes', 'timeline', 'vitals', 'labs', 'imaging', 'prescriptions', 'admissions', 'info'] : ['info']
  return (
    <Modal title={`${patient.first_name} ${patient.last_name} · ${patient.mrn}`} onClose={onClose}>
      <p>{age(patient.dob)} y · {patient.sex} · blood {patient.blood_type || '?'} {patient.allergies && <Badge kind="bad">Allergy: {patient.allergies}</Badge>}</p>
      <div className="tabs">{tabs.map((t) => <button key={t} className={`tab ${t === tab ? 'active' : ''}`} onClick={() => setTab(t)}>{t}</button>)}</div>
      {tab === 'info' && <div className="grid cols-2">
        <div><h3>Contact</h3><p>{patient.phone || '—'}<br />{patient.address || '—'}<br />Emergency: {patient.emergency_contact || '—'}</p></div>
        <div><h3>Insurance</h3><p>{patient.insurance_provider || '—'}<br />{patient.insurance_number || ''}</p></div>
      </div>}
      {tab === 'notes' && <Notes pid={patient.id} canWrite={['doctor', 'surgeon', 'admin'].includes(user.role)} />}
      {tab === 'timeline' && <Timeline pid={patient.id} />}
      {tab === 'vitals' && <Vitals pid={patient.id} />}
      {tab === 'labs' && <Simple path={`/patients/${patient.id}/labs`} cols={[
        { h: 'Test', render: (l) => l.test_name }, { h: 'Status', render: (l) => <Status value={l.status} /> },
        { h: 'Result', render: (l) => (l.result ? <>{l.result} {l.abnormal && <Badge kind="bad">abnormal</Badge>}</> : '—') }, { h: 'Ordered', render: (l) => fmtDateTime(l.ordered_at) }]} />}
      {tab === 'imaging' && <Simple path={`/patients/${patient.id}/imaging`} cols={[
        { h: 'Study', render: (o) => `${o.modality.toUpperCase()} · ${o.body_part}` }, { h: 'Status', render: (o) => <><Status value={o.status} />{o.critical && <> <Badge kind="bad">critical</Badge></>}</> },
        { h: 'Report', render: (o) => o.report || '—' }, { h: 'Ordered', render: (o) => fmtDateTime(o.ordered_at) }]} />}
      {tab === 'admissions' && <Simple path={`/admissions?status=all&patient_id=${patient.id}`} cols={[
        { h: 'Admitted', render: (a) => fmtDateTime(a.admitted_at) }, { h: 'Reason', render: (a) => a.reason }, { h: 'Bed', render: (a) => (a.bed_label ? `${a.ward} · ${a.bed_label}` : '—') },
        { h: 'Status', render: (a) => <Status value={a.status} /> }, { h: 'Discharge summary', render: (a) => a.discharge_summary || '—' }]} />}
      {tab === 'prescriptions' && <Simple path={`/patients/${patient.id}/prescriptions`} cols={[
        { h: 'Drug', render: (r) => r.drug_name }, { h: 'Dosage', render: (r) => `${r.dosage} ×${r.quantity}` },
        { h: 'By', render: (r) => r.prescriber_name }, { h: 'Status', render: (r) => <Status value={r.status} /> }]} />}
    </Modal>
  )
}

const KIND_STYLE = { note: 'info', vitals: '', lab: 'warn', imaging: 'info', prescription: 'ok', admission: 'ok', er: 'bad', surgery: 'warn' }

function Timeline({ pid }) {
  const s = useApi(`/patients/${pid}/timeline?limit=200`, { topics: ['patients', 'labs', 'imaging', 'pharmacy', 'admissions', 'er', 'surgery'] })
  const [kind, setKind] = useState('')
  const kinds = [...new Set((s.data || []).map((e) => e.kind))]
  const rows = (s.data || []).filter((e) => !kind || e.kind === kind)
  return (
    <>
      <Loading state={s} />
      {s.data && s.data.length > 0 && (
        <div className="row" style={{ marginBottom: 10 }}>
          <button className={`btn sm ${kind ? 'ghost' : ''}`} onClick={() => setKind('')}>All</button>
          {kinds.map((k) => <button key={k} className={`btn sm ${kind === k ? '' : 'ghost'}`} onClick={() => setKind(k)}>{k}</button>)}
        </div>
      )}
      {s.data?.length === 0 && <p className="muted">Nothing recorded yet.</p>}
      <ol className="timeline">
        {rows.map((e, i) => (
          <li key={i} className={e.flag ? 'flag' : ''}>
            <div className="row"><Badge kind={KIND_STYLE[e.kind]}>{e.kind}</Badge><b>{e.title}</b>{e.flag && <Badge kind="bad">attention</Badge>}</div>
            {e.detail && <div style={{ whiteSpace: 'pre-wrap' }}>{e.detail}</div>}
            <div className="muted small">{fmtDateTime(e.at)}{e.by ? ` · ${e.by}` : ''}</div>
          </li>
        ))}
      </ol>
    </>
  )
}

function Simple({ path, cols }) {
  const s = useApi(path)
  return <><Loading state={s} /><Table rows={s.data} cols={cols} empty="No records." /></>
}

function Notes({ pid, canWrite }) {
  const s = useApi(`/patients/${pid}/notes`)
  const [text, setText] = useState('')
  const [kind, setKind] = useState('progress')
  const act = useAction(async () => { setText(''); await s.reload() })
  return (
    <>
      {canWrite && <div style={{ marginBottom: 14 }}>
        {act.banner}
        <div className="row" style={{ marginBottom: 8 }}>
          <select value={kind} onChange={(e) => setKind(e.target.value)} style={{ width: 160 }}><option>progress</option><option>diagnosis</option><option>discharge</option></select>
        </div>
        <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Clinical note…" />
        <p><button className="btn" disabled={act.busy || !text.trim()} onClick={() => act.run(() => api.post(`/patients/${pid}/notes`, { kind, text }))}>Add note</button></p>
      </div>}
      <Loading state={s} />
      {(s.data || []).map((n) => (
        <div key={n.id} className="card" style={{ marginBottom: 8 }}>
          <div className="row"><Badge kind="info">{n.kind}</Badge><span className="muted small">{n.author_name} · {fmtDateTime(n.at)}</span></div>
          <p style={{ whiteSpace: 'pre-wrap', margin: '8px 0 0' }}>{n.text}</p>
        </div>
      ))}
      {s.data?.length === 0 && <p className="muted">No notes yet.</p>}
    </>
  )
}

function Vitals({ pid }) {
  const s = useApi(`/patients/${pid}/vitals`)
  const [f, setF] = useState({ heart_rate: '', systolic: '', diastolic: '', temperature_c: '', spo2: '', resp_rate: '' })
  const act = useAction(async () => { setF({ heart_rate: '', systolic: '', diastolic: '', temperature_c: '', spo2: '', resp_rate: '' }); await s.reload() })
  const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === '' ? null : Number(v)]))
  const lab = { heart_rate: 'HR', systolic: 'Sys', diastolic: 'Dia', temperature_c: 'Temp °C', spo2: 'SpO₂ %', resp_rate: 'RR' }
  return (
    <>
      {act.banner}
      <div className="form">{Object.keys(f).map((k) => <Field key={k} label={lab[k]}><input type="number" step="any" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>)}</div>
      <p><button className="btn" disabled={act.busy || Object.values(f).every((v) => v === '')} onClick={() => act.run(() => api.post(`/patients/${pid}/vitals`, body))}>Record vitals</button></p>
      <Loading state={s} />
      <Table rows={s.data} empty="No vitals recorded." cols={[
        { h: 'When', render: (v) => fmtDateTime(v.at) }, { h: 'HR', render: (v) => v.heart_rate ?? '—' },
        { h: 'BP', render: (v) => (v.systolic ? `${v.systolic}/${v.diastolic ?? '?'}` : '—') }, { h: 'Temp', render: (v) => v.temperature_c ?? '—' },
        { h: 'SpO₂', render: (v) => (v.spo2 != null ? <span style={{ color: v.spo2 < 94 ? 'var(--bad)' : undefined }}>{v.spo2}%</span> : '—') }, { h: 'RR', render: (v) => v.resp_rate ?? '—' }]} />
    </>
  )
}
