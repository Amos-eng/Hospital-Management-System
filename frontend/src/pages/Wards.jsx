import { useState } from 'react'
import { api } from '../api'
import { Badge, Field, Loading, Modal, Table, fmtDateTime, useAction, useApi } from '../ui'

const DOCTORS = ['doctor', 'surgeon', 'admin']

export default function Wards({ user }) {
  const wards = useApi('/wards', { topics: ['beds', 'admissions'], poll: 60000 })
  const adm = useApi('/admissions', { topics: ['admissions'], poll: 60000 })
  const [admit, setAdmit] = useState(false)
  const [transfer, setTransfer] = useState(null)
  const [discharge, setDischarge] = useState(null)
  const [sel, setSel] = useState(null)
  const isDoc = DOCTORS.includes(user.role)
  const refresh = async () => { await Promise.all([wards.reload(), adm.reload()]) }

  return (
    <>
      <div className="header">
        <div><h1>Inpatient wards</h1><span className="muted">Bed map, admissions, transfers and discharge</span></div>
        {isDoc && <button className="btn" onClick={() => setAdmit(true)}>+ Admit patient</button>}
      </div>
      <Loading state={wards} />
      <div className="grid cols-2" style={{ marginBottom: 14 }}>
        {(wards.data || []).map((w) => (
          <div className="card" key={w.ward}>
            <div className="ward-title"><h2>{w.ward}</h2><span className="muted small">{w.occupied}/{w.total} occupied</span></div>
            <div className="bed-grid">
              {w.beds.map((b) => (
                <button key={b.id} className={`bed ${b.occupied ? 'occ' : 'free'}`} style={{ cursor: b.occupied ? 'pointer' : 'default', textAlign: 'left' }}
                  onClick={() => b.occupied && setSel(adm.data?.find((a) => a.id === b.admission_id) || null)}
                  title={b.reason || 'Free'}>
                  {b.label}{b.occupied && <small>{b.patient_name}</small>}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="card">
        <h2>Current inpatients</h2>
        <Loading state={adm} />
        <Table empty="No inpatients." rows={adm.data} cols={[
          { h: 'Patient', render: (a) => <><b>{a.patient_name}</b> <span className="muted small">{a.mrn}</span>{a.allergies && <><br /><Badge kind="bad">Allergy: {a.allergies}</Badge></>}</> },
          { h: 'Bed', render: (a) => `${a.ward} · ${a.bed_label}` },
          { h: 'Reason', render: (a) => a.reason },
          { h: 'Attending', render: (a) => a.attending_name },
          { h: 'Admitted', render: (a) => <>{fmtDateTime(a.admitted_at)}<br /><span className="muted small">day {a.los_days + 1} · via {a.source === 'er' ? 'ER' : 'direct'}</span></> },
          { h: '', render: (a) => (
            <div className="row">
              <button className="btn sm ghost" onClick={() => setTransfer(a)}>Transfer</button>
              {isDoc && <button className="btn sm ghost" onClick={() => setDischarge(a)}>Discharge</button>}
            </div>) },
        ]} />
      </div>
      {admit && <AdmitModal onClose={() => setAdmit(false)} onDone={async () => { setAdmit(false); await refresh() }} />}
      {transfer && <Transfer a={transfer} wards={wards.data || []} onClose={() => setTransfer(null)} onDone={async () => { setTransfer(null); await refresh() }} />}
      {discharge && <Discharge a={discharge} onClose={() => setDischarge(null)} onDone={async () => { setDischarge(null); await refresh() }} />}
      {sel && (
        <Modal title={`${sel.patient_name} · ${sel.bed_label}`} onClose={() => setSel(null)}>
          <p>{sel.reason}<br /><span className="muted">Attending {sel.attending_name} · admitted {fmtDateTime(sel.admitted_at)}</span></p>
          <h3>Bed history</h3>
          {sel.transfers.length === 0 ? <p className="muted">No transfers.</p> : sel.transfers.map((t, i) => <p key={i} className="small">{fmtDateTime(t.at)} · {t.from_bed || '—'} → {t.to_bed}</p>)}
        </Modal>
      )}
    </>
  )
}

/** Admit a patient to a ward bed. With `preset`, this closes an open ER visit as admitted. */
export function AdmitModal({ preset, onClose, onDone }) {
  const patients = useApi('/patients?limit=200')
  const wards = useApi('/wards')
  const staff = useApi('/staff')
  const [pid, setPid] = useState(preset?.patient_id || '')
  const [bed, setBed] = useState('')
  const [doc, setDoc] = useState('')
  const [reason, setReason] = useState(preset?.complaint || '')
  const act = useAction(onDone)
  const doctors = (staff.data || []).filter((s) => ['doctor', 'surgeon'].includes(s.role))
  return (
    <Modal title={preset ? `Admit from ER — ${preset.patient_name}` : 'Admit patient'} onClose={onClose}>
      {act.banner}
      <div className="form">
        {!preset && (
          <Field label="Patient">
            <select value={pid} onChange={(e) => setPid(e.target.value)}>
              <option value="">Select…</option>
              {(patients.data || []).map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name} · {p.mrn}</option>)}
            </select>
          </Field>
        )}
        <Field label="Ward bed">
          <select value={bed} onChange={(e) => setBed(e.target.value)}>
            <option value="">Select…</option>
            {(wards.data || []).map((w) => (
              <optgroup key={w.ward} label={w.ward}>
                {w.beds.filter((b) => !b.occupied).map((b) => <option key={b.id} value={b.id}>{b.label}</option>)}
              </optgroup>
            ))}
          </select>
        </Field>
        <Field label="Attending">
          <select value={doc} onChange={(e) => setDoc(e.target.value)}>
            <option value="">Select…</option>
            {doctors.map((d) => <option key={d.id} value={d.id}>{d.full_name} · {d.specialty}</option>)}
          </select>
        </Field>
      </div>
      <div style={{ margin: '12px 0' }}><Field label="Reason for admission"><input value={reason} onChange={(e) => setReason(e.target.value)} /></Field></div>
      <button className="btn" disabled={act.busy || !pid || !bed || !doc || !reason.trim()}
        onClick={() => act.run(() => api.post('/admissions', { patient_id: +pid, bed_id: +bed, attending_id: +doc, reason, er_visit_id: preset?.er_visit_id ?? null }))}>Admit</button>
    </Modal>
  )
}

function Transfer({ a, wards, onClose, onDone }) {
  const [bed, setBed] = useState('')
  const act = useAction(onDone)
  return (
    <Modal title={`Transfer — ${a.patient_name}`} onClose={onClose}>
      {act.banner}
      <p className="muted">Currently in {a.ward} · {a.bed_label}</p>
      <Field label="New bed">
        <select value={bed} onChange={(e) => setBed(e.target.value)}>
          <option value="">Select…</option>
          {wards.map((w) => <optgroup key={w.ward} label={w.ward}>{w.beds.filter((b) => !b.occupied).map((b) => <option key={b.id} value={b.id}>{b.label}</option>)}</optgroup>)}
        </select>
      </Field>
      <p><button className="btn" disabled={act.busy || !bed} onClick={() => act.run(() => api.post(`/admissions/${a.id}/transfer`, { bed_id: +bed }))}>Transfer</button></p>
    </Modal>
  )
}

function Discharge({ a, onClose, onDone }) {
  const [summary, setSummary] = useState('')
  const act = useAction(onDone)
  return (
    <Modal title={`Discharge — ${a.patient_name}`} onClose={onClose}>
      {act.banner}
      <Field label="Discharge summary"><textarea rows={5} value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="Diagnosis, treatment given, medications, follow-up…" /></Field>
      <p><button className="btn" disabled={act.busy || summary.trim().length < 5} onClick={() => act.run(() => api.post(`/admissions/${a.id}/discharge`, { summary }))}>Discharge patient</button></p>
    </Modal>
  )
}
