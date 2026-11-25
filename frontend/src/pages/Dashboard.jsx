import { Loading, tzOffset, useApi } from '../ui'

const TILES = [
  ['er_waiting', 'ER waiting', (v) => v > 3 && 'alert'],
  ['er_in_treatment', 'ER in treatment'],
  ['er_critical', 'Critical (ESI 1–2)', (v) => v > 0 && 'alert'],
  ['surgeries_today', 'Surgeries today'],
  ['surgeries_in_progress', 'In the OR now', (v) => v > 0 && 'good'],
  ['appointments_today', 'Appointments today'],
  ['labs_pending', 'Labs pending'],
  ['rx_pending', 'Rx awaiting pharmacy'],
  ['low_stock_drugs', 'Low-stock drugs', (v) => v > 0 && 'alert'],
  ['inpatients', 'Inpatients'],
  ['imaging_pending', 'Imaging in progress'],
  ['staff_on_duty', 'Staff on duty now'],
  ['patients', 'Patients on file'],
]

const barColor = (pct) => (pct >= 90 ? 'var(--bad)' : pct >= 75 ? 'var(--warn)' : 'var(--ok)')

function Occupancy({ wards }) {
  return (
    <div className="card" style={{ marginTop: 14 }}>
      <h2>Bed occupancy</h2>
      <div className="grid" style={{ gap: 12 }}>
        {wards.map((w) => (
          <div key={w.ward}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <b>{w.ward}</b><span className="muted small">{w.occupied}/{w.total} beds · {w.percent}%</span>
            </div>
            <div className="meter" role="progressbar" aria-label={`${w.ward} occupancy`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={w.percent}>
              <div style={{ width: `${w.percent}%`, background: barColor(w.percent) }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Dashboard({ user }) {
  const s = useApi(`/dashboard?tz_offset=${tzOffset()}`, { poll: 60000, topics: ['er', 'beds', 'surgery', 'labs', 'imaging', 'admissions', 'roster', 'pharmacy', 'appointments', 'billing', 'patients'] })
  const d = s.data
  return (
    <>
      <div className="header">
        <div><h1>Good day, {user.full_name.split(' ')[0] === 'Dr.' ? user.full_name.split(' ')[1] : user.full_name.split(' ')[0]}</h1><span className="muted">Live hospital overview · updates as things happen</span></div>
      </div>
      <Loading state={s} />
      {d && (
        <>
          <div className="grid cols-4">
            {TILES.map(([k, label, kind]) => (
              <div key={k} className={`card stat ${kind?.(d[k]) || ''}`}><div className="v">{d[k]}</div><div className="l">{label}</div></div>
            ))}
            <div className="card stat">
              <div className="v">{d.beds_occupied}/{d.beds_total}</div><div className="l">Beds occupied</div>
            </div>
            <div className="card stat">
              <div className="v">{Number(d.open_balance).toLocaleString(undefined, { style: 'currency', currency: 'USD' })}</div><div className="l">Open invoices</div>
            </div>
          </div>
          <Occupancy wards={d.ward_occupancy || []} />
        </>
      )}
    </>
  )
}
