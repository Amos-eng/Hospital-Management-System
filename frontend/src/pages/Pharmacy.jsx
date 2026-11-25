import { useState } from 'react'
import { api } from '../api'
import { Badge, Field, Loading, Status, Table, fmtDateTime, money, useAction, useApi } from '../ui'

export default function Pharmacy({ user }) {
  const isPharm = ['pharmacist', 'admin'].includes(user.role)
  const canPrescribe = ['doctor', 'surgeon', 'admin'].includes(user.role)
  const rx = useApi('/prescriptions', { poll: 60000, topics: ['pharmacy'] })
  const drugs = useApi('/drugs', { topics: ['pharmacy'] })
  const refresh = async () => { await Promise.all([rx.reload(), drugs.reload()]) }
  const act = useAction(refresh)
  const [add, setAdd] = useState(1)

  return (
    <>
      <div className="header"><div><h1>Pharmacy</h1><span className="muted">Dispensing checks stock and patient allergies</span></div></div>
      {act.banner}
      {canPrescribe && <Prescribe drugs={drugs.data || []} onDone={refresh} />}
      <div className="card" style={{ marginBottom: 14 }}>
        <h2>Prescriptions</h2>
        <Loading state={rx} />
        <Table empty="No prescriptions." rows={rx.data} cols={[
          { h: 'Patient', render: (r) => r.patient_name }, { h: 'Drug', render: (r) => <><b>{r.drug_name}</b><br /><span className="muted small">{r.dosage} ×{r.quantity}</span></> },
          { h: 'Prescriber', render: (r) => r.prescriber_name }, { h: 'Written', render: (r) => fmtDateTime(r.created_at) },
          { h: 'Status', render: (r) => <Status value={r.status} /> },
          { h: '', render: (r) => isPharm && r.status === 'pending' && <button className="btn sm" disabled={act.busy} onClick={() => act.run(() => api.post(`/prescriptions/${r.id}/dispense`), 'Dispensed')}>Dispense</button> },
        ]} />
      </div>
      <div className="card">
        <h2>Inventory</h2>
        <Loading state={drugs} />
        <Table rows={drugs.data} cols={[
          { h: 'Drug', render: (d) => d.name }, { h: 'Form', render: (d) => d.form }, { h: 'Unit price', render: (d) => money(d.unit_price) },
          { h: 'Stock', render: (d) => <>{d.stock} {d.low_stock && <Badge kind="bad">low</Badge>}</> },
          { h: '', render: (d) => isPharm && <button className="btn sm ghost" disabled={act.busy} onClick={() => act.run(() => api.post(`/drugs/${d.id}/restock`, { quantity: 100 }), `Restocked ${d.name} (+100)`)}>+100</button> },
        ]} />
      </div>
    </>
  )
}

function Prescribe({ drugs, onDone }) {
  const patients = useApi('/patients?limit=200')
  const [f, setF] = useState({ patient_id: '', drug_id: '', dosage: '', quantity: 1 })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const act = useAction(async () => { setF({ patient_id: '', drug_id: '', dosage: '', quantity: 1 }); await onDone() })
  const p = (patients.data || []).find((x) => x.id === +f.patient_id)
  const d = drugs.find((x) => x.id === +f.drug_id)
  const clash = p?.allergies && d && p.allergies.toLowerCase().includes(d.name.toLowerCase())
  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <h2>New prescription</h2>
      {act.banner}
      {clash && <div className="error">Allergy alert: {p.first_name} is allergic to {p.allergies}.</div>}
      <div className="form">
        <Field label="Patient"><select value={f.patient_id} onChange={set('patient_id')}><option value="">Select…</option>{(patients.data || []).map((x) => <option key={x.id} value={x.id}>{x.first_name} {x.last_name}{x.allergies ? ` ⚠ ${x.allergies}` : ''}</option>)}</select></Field>
        <Field label="Drug"><select value={f.drug_id} onChange={set('drug_id')}><option value="">Select…</option>{drugs.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
        <Field label="Dosage"><input value={f.dosage} onChange={set('dosage')} placeholder="1 tab every 8h" /></Field>
        <Field label="Quantity"><input type="number" min="1" value={f.quantity} onChange={set('quantity')} /></Field>
        <button className="btn" disabled={act.busy || !f.patient_id || !f.drug_id || !f.dosage.trim() || +f.quantity < 1}
          onClick={() => act.run(() => api.post('/prescriptions', { patient_id: +f.patient_id, drug_id: +f.drug_id, dosage: f.dosage, quantity: +f.quantity }), 'Prescription sent to pharmacy')}>Prescribe</button>
      </div>
    </div>
  )
}
