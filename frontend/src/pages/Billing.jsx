import { useState } from 'react'
import { api } from '../api'
import { Field, Loading, Status, Table, fmtDateTime, money, useAction, useApi } from '../ui'

export default function Billing({ user }) {
  const [filter, setFilter] = useState('')
  const list = useApi(`/invoices${filter ? `?status=${filter}` : ''}`, { topics: ['billing'] })
  const canEdit = ['billing', 'admin'].includes(user.role)
  const act = useAction(list.reload)
  const [pay, setPay] = useState({}) // id -> {amount, method}

  return (
    <>
      <div className="header">
        <div><h1>Billing</h1><span className="muted">Invoices, payments and balances</span></div>
        <select value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: 160 }}><option value="">All</option><option>open</option><option>paid</option><option>void</option></select>
      </div>
      {act.banner}
      {canEdit && <NewInvoice onDone={list.reload} />}
      <div className="card">
        <Loading state={list} />
        <Table empty="No invoices." rows={list.data} cols={[
          { h: '#', render: (i) => i.id }, { h: 'Patient', render: (i) => <><b>{i.patient_name}</b><br /><span className="muted small">{fmtDateTime(i.created_at)}</span></> },
          { h: 'Items', render: (i) => i.items.map((it) => `${it.description} ×${it.quantity}`).join('; ') },
          { h: 'Total', render: (i) => money(i.total) }, { h: 'Paid', render: (i) => money(i.paid) },
          { h: 'Balance', render: (i) => <b style={{ color: i.balance > 0 && i.status === 'open' ? 'var(--warn)' : undefined }}>{money(i.balance)}</b> },
          { h: 'Status', render: (i) => <Status value={i.status} /> },
          { h: '', render: (i) => {
            if (!canEdit || i.status !== 'open') return null
            const p = pay[i.id] || { amount: i.balance, method: 'cash' }
            return (
              <div className="row">
                <input type="number" step="0.01" style={{ width: 90 }} value={p.amount} onChange={(e) => setPay({ ...pay, [i.id]: { ...p, amount: e.target.value } })} />
                <select style={{ width: 120 }} value={p.method} onChange={(e) => setPay({ ...pay, [i.id]: { ...p, method: e.target.value } })}><option value="cash">cash</option><option value="card">card</option><option value="insurance">insurance</option><option value="mobile_money">mobile money</option></select>
                <button className="btn sm" disabled={act.busy || !(+p.amount > 0)} onClick={() => act.run(() => api.post(`/invoices/${i.id}/pay`, { amount: +p.amount, method: p.method }), 'Payment recorded')}>Pay</button>
                <button className="btn sm danger" disabled={act.busy} onClick={() => act.run(() => api.post(`/invoices/${i.id}/void`), 'Invoice voided')}>Void</button>
              </div>
            )
          } },
        ]} />
      </div>
    </>
  )
}

function NewInvoice({ onDone }) {
  const patients = useApi('/patients?limit=200')
  const [pid, setPid] = useState('')
  const [items, setItems] = useState([{ description: '', quantity: 1, unit_price: '' }])
  const act = useAction(async () => { setPid(''); setItems([{ description: '', quantity: 1, unit_price: '' }]); await onDone() })
  const upd = (i, k, v) => setItems(items.map((it, j) => (j === i ? { ...it, [k]: v } : it)))
  const valid = pid && items.every((it) => it.description.trim() && +it.quantity > 0 && it.unit_price !== '' && +it.unit_price >= 0)
  const total = items.reduce((s, it) => s + (+it.quantity || 0) * (+it.unit_price || 0), 0)
  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <h2>New invoice</h2>
      <Field label="Patient"><select value={pid} onChange={(e) => setPid(e.target.value)}><option value="">Select…</option>{(patients.data || []).map((p) => <option key={p.id} value={p.id}>{p.first_name} {p.last_name} · {p.mrn}</option>)}</select></Field>
      {items.map((it, i) => (
        <div key={i} className="row" style={{ marginTop: 8 }}>
          <input style={{ flex: 1, minWidth: 200 }} placeholder="Description" value={it.description} onChange={(e) => upd(i, 'description', e.target.value)} />
          <input type="number" min="1" style={{ width: 80 }} value={it.quantity} onChange={(e) => upd(i, 'quantity', e.target.value)} />
          <input type="number" step="0.01" min="0" style={{ width: 110 }} placeholder="Unit price" value={it.unit_price} onChange={(e) => upd(i, 'unit_price', e.target.value)} />
          {items.length > 1 && <button className="btn sm ghost" onClick={() => setItems(items.filter((_, j) => j !== i))}>Remove</button>}
        </div>
      ))}
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn ghost sm" onClick={() => setItems([...items, { description: '', quantity: 1, unit_price: '' }])}>+ Line</button>
        <b>Total {money(total)}</b>
        <button className="btn" disabled={act.busy || !valid} onClick={() => act.run(() => api.post('/invoices', { patient_id: +pid, items: items.map((it) => ({ ...it, quantity: +it.quantity, unit_price: +it.unit_price })) }), 'Invoice created')}>Create invoice</button>
      </div>
      {act.banner}
    </div>
  )
}
