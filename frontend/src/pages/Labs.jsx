import { useState } from 'react'
import { api } from '../api'
import { Badge, Field, Loading, Status, Table, fmtDateTime, useAction, useApi } from '../ui'

const TESTS = ['Full blood count', 'Troponin I', 'Basic metabolic panel', 'Liver function', 'Urinalysis', 'Blood culture', 'Coagulation (PT/INR)', 'Blood glucose', 'Type & crossmatch']

export default function Labs({ user }) {
  const list = useApi('/labs', { poll: 60000, topics: ['labs'] })
  const act = useAction(list.reload)
  const isLab = ['lab_tech', 'admin'].includes(user.role)
  const canOrder = ['doctor', 'surgeon', 'nurse', 'admin'].includes(user.role)
  const canCollect = ['lab_tech', 'nurse', 'admin'].includes(user.role)
  const [resulting, setResulting] = useState({}) // id -> {result, abnormal}

  return (
    <>
      <div className="header"><div><h1>Laboratory</h1><span className="muted">STAT orders float to the top</span></div></div>
      {act.banner}
      {canOrder && <Order onDone={list.reload} />}
      <div className="card">
        <Loading state={list} />
        <Table empty="No lab orders." rows={list.data} cols={[
          { h: 'Priority', render: (l) => (l.priority === 'stat' ? <Badge kind="bad">STAT</Badge> : 'routine') },
          { h: 'Test', render: (l) => <><b>{l.test_name}</b><br /><span className="muted small">{l.patient_name} · by {l.ordered_by_name}</span></> },
          { h: 'Ordered', render: (l) => fmtDateTime(l.ordered_at) }, { h: 'Status', render: (l) => <Status value={l.status} /> },
          { h: 'Result', render: (l) => {
            if (l.status === 'resulted') return <>{l.result} {l.abnormal && <Badge kind="bad">abnormal</Badge>}</>
            if (l.status === 'collected' && isLab) {
              const r = resulting[l.id] || { result: '', abnormal: false }
              return (
                <div className="row">
                  <input style={{ width: 180 }} placeholder="Result" value={r.result} onChange={(e) => setResulting({ ...resulting, [l.id]: { ...r, result: e.target.value } })} />
                  <label className="row small" style={{ margin: 0 }}><input type="checkbox" style={{ width: 'auto' }} checked={r.abnormal} onChange={(e) => setResulting({ ...resulting, [l.id]: { ...r, abnormal: e.target.checked } })} />abnormal</label>
                  <button className="btn sm" disabled={act.busy || !r.result.trim()} onClick={() => act.run(() => api.post(`/labs/${l.id}/result`, r), 'Result saved')}>Save</button>
                </div>
              )
            }
            return '—'
          } },
          { h: '', render: (l) => l.status === 'ordered' && canCollect && <button className="btn sm ghost" disabled={act.busy} onClick={() => act.run(() => api.post(`/labs/${l.id}/collect`), 'Sample collected')}>Collect sample</button> },
        ]} />
      </div>
    </>
  )
}

function Order({ onDone }) {
  const patients = useApi('/patients?limit=200')
  const [f, setF] = useState({ patient_id: '', test_name: TESTS[0], priority: 'routine' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const act = useAction(onDone)
  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <h2>Order a test</h2>
      {act.banner}
      <div className="form">
        <Field label="Patient"><select value={f.patient_id} onChange={set('patient_id')}><option value="">Select…</option>{(patients.data || []).map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name} · {p.mrn}</option>)}</select></Field>
        <Field label="Test"><select value={f.test_name} onChange={set('test_name')}>{TESTS.map((t) => <option key={t}>{t}</option>)}</select></Field>
        <Field label="Priority"><select value={f.priority} onChange={set('priority')}><option>routine</option><option>stat</option></select></Field>
        <button className="btn" disabled={act.busy || !f.patient_id} onClick={() => act.run(() => api.post('/labs', { ...f, patient_id: +f.patient_id }), 'Lab ordered')}>Order</button>
      </div>
    </div>
  )
}
