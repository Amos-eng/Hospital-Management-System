import { useState } from 'react'
import { api } from '../api'
import { Badge, Field, Loading, Modal, Status, Table, fmtDateTime, nowLocalInput, toApiTime, useAction, useApi } from '../ui'

const MODALITY = { xray: 'X-ray', ct: 'CT', mri: 'MRI', ultrasound: 'Ultrasound' }
const prioKind = { stat: 'bad', urgent: 'warn', routine: '' }

export default function Imaging({ user }) {
  const [filter, setFilter] = useState('')
  const list = useApi(`/imaging${filter ? `?status=${filter}` : ''}`, { topics: ['imaging'], poll: 60000 })
  const act = useAction(list.reload)
  const isRad = ['radiologist', 'admin'].includes(user.role)
  const canOrder = ['doctor', 'surgeon', 'nurse', 'admin'].includes(user.role)
  const canSchedule = isRad || user.role === 'nurse'
  const [report, setReport] = useState(null)
  const [sched, setSched] = useState(null)
  const [view, setView] = useState(null)

  return (
    <>
      <div className="header">
        <div><h1>Radiology &amp; imaging</h1><span className="muted">STAT studies first · ordered → scheduled → performed → reported</span></div>
        <select value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: 170 }}>
          <option value="">All studies</option>{['ordered', 'scheduled', 'performed', 'reported', 'cancelled'].map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      {act.banner}
      {canOrder && <Order onDone={list.reload} />}
      <div className="card">
        <Loading state={list} />
        <Table empty="No imaging orders." rows={list.data} cols={[
          { h: 'Priority', render: (o) => <Badge kind={prioKind[o.priority]}>{o.priority.toUpperCase()}</Badge> },
          { h: 'Study', render: (o) => <><b>{MODALITY[o.modality]} · {o.body_part}</b>{o.contrast && <> <Badge kind="info">contrast</Badge></>}<br /><span className="muted small">{o.patient_name} · by {o.ordered_by_name}</span>{o.clinical_info && <><br /><span className="muted small">{o.clinical_info}</span></>}</> },
          { h: 'Status', render: (o) => <><Status value={o.status} />{o.critical && <> <Badge kind="bad">CRITICAL</Badge></>}<br /><span className="muted small">{o.scheduled_at && o.status === 'scheduled' ? `slot ${fmtDateTime(o.scheduled_at)}` : fmtDateTime(o.ordered_at)}</span></> },
          { h: '', render: (o) => (
            <div className="row">
              {o.status === 'reported' && <button className="btn sm ghost" onClick={() => setView(o)}>View report</button>}
              {canSchedule && ['ordered', 'scheduled'].includes(o.status) && <button className="btn sm ghost" onClick={() => setSched(o)}>{o.status === 'scheduled' ? 'Reschedule' : 'Schedule'}</button>}
              {isRad && ['ordered', 'scheduled'].includes(o.status) && <button className="btn sm" disabled={act.busy} onClick={() => act.run(() => api.post(`/imaging/${o.id}/perform`), 'Marked as performed')}>Perform</button>}
              {isRad && o.status === 'performed' && <button className="btn sm" onClick={() => setReport(o)}>Write report</button>}
              {(canOrder || isRad) && !['reported', 'cancelled'].includes(o.status) && <button className="btn sm danger" disabled={act.busy} onClick={() => window.confirm('Cancel this study?') && act.run(() => api.post(`/imaging/${o.id}/cancel`), 'Cancelled')}>Cancel</button>}
            </div>) },
        ]} />
      </div>
      {sched && <Schedule o={sched} onClose={() => setSched(null)} onDone={async () => { setSched(null); await list.reload() }} />}
      {report && <Report o={report} onClose={() => setReport(null)} onDone={async () => { setReport(null); await list.reload() }} />}
      {view && (
        <Modal title={`${MODALITY[view.modality]} ${view.body_part} — ${view.patient_name}`} onClose={() => setView(null)}>
          <p>{view.critical && <Badge kind="bad">CRITICAL FINDING</Badge>} <span className="muted small">Reported by {view.radiologist_name} · {fmtDateTime(view.reported_at)}</span></p>
          <p style={{ whiteSpace: 'pre-wrap' }}>{view.report}</p>
        </Modal>
      )}
    </>
  )
}

function Order({ onDone }) {
  const patients = useApi('/patients?limit=200')
  const [f, setF] = useState({ patient_id: '', modality: 'xray', body_part: '', clinical_info: '', contrast: false, priority: 'routine', override_allergy: false })
  const set = (k) => (e) => setF({ ...f, [k]: e.type === 'change' && e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const act = useAction(async () => { setF({ ...f, body_part: '', clinical_info: '', contrast: false, override_allergy: false }); await onDone() })
  const allergyBlock = act.error.startsWith('Allergy warning')
  const noContrast = f.modality === 'xray' || f.modality === 'ultrasound'
  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <h2>Order imaging</h2>
      {act.banner}
      <div className="form">
        <Field label="Patient"><select value={f.patient_id} onChange={set('patient_id')}><option value="">Select…</option>{(patients.data || []).map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name}{p.allergies ? ` ⚠ ${p.allergies}` : ''}</option>)}</select></Field>
        <Field label="Modality"><select value={f.modality} onChange={(e) => setF({ ...f, modality: e.target.value, contrast: ['xray', 'ultrasound'].includes(e.target.value) ? false : f.contrast })}>{Object.entries(MODALITY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        <Field label="Body part"><input value={f.body_part} onChange={set('body_part')} placeholder="e.g. Chest" /></Field>
        <Field label="Priority"><select value={f.priority} onChange={set('priority')}><option>routine</option><option>urgent</option><option>stat</option></select></Field>
        <Field label="Clinical information"><input value={f.clinical_info} onChange={set('clinical_info')} placeholder="Reason for the study" /></Field>
        <label className="row" style={{ margin: 0, color: noContrast ? 'var(--muted)' : undefined }}><input type="checkbox" style={{ width: 'auto' }} disabled={noContrast} checked={f.contrast} onChange={set('contrast')} />With contrast</label>
        {allergyBlock && <label className="row" style={{ margin: 0, color: 'var(--warn)' }}><input type="checkbox" style={{ width: 'auto' }} checked={f.override_allergy} onChange={set('override_allergy')} />Override allergy warning (clinically justified)</label>}
        <button className="btn" disabled={act.busy || !f.patient_id || !f.body_part.trim()}
          onClick={() => act.run(() => api.post('/imaging', { ...f, clinical_info: f.clinical_info || null, patient_id: +f.patient_id }), 'Imaging ordered')}>Order</button>
      </div>
    </div>
  )
}

function Schedule({ o, onClose, onDone }) {
  const [at, setAt] = useState(nowLocalInput(1))
  const act = useAction(onDone)
  return (
    <Modal title={`Schedule ${MODALITY[o.modality]} — ${o.patient_name}`} onClose={onClose}>
      {act.banner}
      <p className="muted">One {MODALITY[o.modality]} scanner: slots are 30 minutes and cannot overlap.</p>
      <Field label="Slot"><input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} /></Field>
      <p><button className="btn" disabled={act.busy || !at} onClick={() => act.run(() => api.post(`/imaging/${o.id}/schedule`, { scheduled_at: toApiTime(at) }))}>Book slot</button></p>
    </Modal>
  )
}

function Report({ o, onClose, onDone }) {
  const [text, setText] = useState('')
  const [critical, setCritical] = useState(false)
  const act = useAction(onDone)
  return (
    <Modal title={`Report — ${MODALITY[o.modality]} ${o.body_part}, ${o.patient_name}`} onClose={onClose}>
      {act.banner}
      {o.clinical_info && <p className="muted">Clinical info: {o.clinical_info}</p>}
      <Field label="Findings and impression"><textarea rows={7} value={text} onChange={(e) => setText(e.target.value)} /></Field>
      <label className="row" style={{ margin: '10px 0', color: critical ? 'var(--bad)' : undefined }}><input type="checkbox" style={{ width: 'auto' }} checked={critical} onChange={(e) => setCritical(e.target.checked)} />Critical finding — alert the ordering clinician immediately</label>
      <button className="btn" disabled={act.busy || text.trim().length < 5} onClick={() => act.run(() => api.post(`/imaging/${o.id}/report`, { report: text, critical }))}>Sign report</button>
    </Modal>
  )
}
