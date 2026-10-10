import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, Camera, ExternalLink, Eye, FileClock, Filter, Plus, Save, Search, X } from 'lucide-react'
import { api } from '../services/api'
import { useUI } from '../state'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState } from '../components/EmptyState'
import { stateSlug, type Inspection, type Measurement } from '../types'
import { assetUrl } from '../services/staticDemo'

const POINTS = ['SD-01', 'SD-02', 'SD-03', 'SD-04']
const SD_SCHEME_URL = assetUrl('schemes/sd_inspection_reference.png')

export function InspectionsPage() {
  const [showForm, setShowForm] = useState(false)
  const [query, setQuery] = useState('')
  const [pointFilter, setPointFilter] = useState('ALL')
  const [selected, setSelected] = useState<Inspection | null>(null)
  const inspections = useQuery({ queryKey: ['inspections'], queryFn: () => api.inspections({ limit: 500 }) })
  const qc = useQueryClient()
  const notify = useUI(s => s.notify)
  const setInspection = useUI(s => s.setInspection)

  const rows = useMemo(() => inspections.data?.filter(inspection => {
    const visible = pointFilter === 'ALL'
      ? inspection.measurements
      : inspection.measurements.filter(measurement => measurement.point === pointFilter)
    if (!visible.length) return false
    const searchable = [inspection.date, inspection.inspector].join(' ').toLowerCase()
    return !query || searchable.includes(query.toLowerCase())
  }) || [], [inspections.data, pointFilter, query])
  const visibleReadingCount = rows.reduce((total, inspection) => total + (
    pointFilter === 'ALL'
      ? inspection.measurements.length
      : inspection.measurements.filter(m => m.point === pointFilter).length
  ), 0)

  return <>
    <PageHeader eyebrow="INSPECTION REGISTER" title="Inspections" description="Registro histórico y nuevas campañas de inspección · Los históricos importados son inmutables." action={<button className="button button-primary" onClick={() => setShowForm(true)}><Plus size={16} /> New inspection</button>} />
    <div className="inspections-summary">
      <div><FileClock size={17} /><span><b>{inspections.data?.length ?? '—'}</b> inspection dates</span></div>
      <div><span>Fuente histórica:</span><b>25 fechas · 100 puntos</b></div>
      <div className="summary-note"><span className="null-key" /> 3 registros históricos N/I preservados como NULL</div>
    </div>
    <section className="panel table-panel">
      <div className="table-toolbar">
        <div><b>Inspection history</b><span>{rows.length} campañas · {visibleReadingCount} lecturas visibles · {pointFilter === 'ALL' ? 'todos los puntos' : pointFilter}</span></div>
        <label className="table-search"><Search size={15} /><input aria-label="Filter by date or inspector" placeholder="Filter date or inspector" value={query} onChange={e => setQuery(e.target.value)} /></label>
        <label className="point-filter"><Filter size={14} /><span className="sr-only">Filter by point</span><select aria-label="Filter inspections by point" value={pointFilter} onChange={e => setPointFilter(e.target.value)}><option value="ALL">All points</option>{POINTS.map(point => <option key={point} value={point}>{point}</option>)}</select></label>
      </div>
      {inspections.isLoading
        ? <div className="page-loading small"><span className="loader-ring" /> Loading inspections…</div>
        : rows.length === 0
          ? <EmptyState title="No matching inspections" />
          : <div className="table-scroll"><table><thead><tr><th>INSPECTION DATE</th><th>HOUR METER</th><th>INSPECTOR</th><th>COMPLETENESS</th><th>CONDITION</th><th>POINT READINGS</th><th></th></tr></thead><tbody>
            {rows.map(inspection => {
              const measurements = pointFilter === 'ALL'
                ? inspection.measurements
                : inspection.measurements.filter(m => m.point === pointFilter)
              const denominator = measurements.length || 1
              const count = {
                normal: measurements.filter(m => m.structural_state === 'Normal').length,
                alert: measurements.filter(m => m.structural_state === 'Alerta').length,
                critical: measurements.filter(m => m.structural_state === 'Crítico').length,
                ni: measurements.filter(m => m.structural_state === 'N/I').length,
              }
              const completeness = measurements.filter(m => m.length_mm !== null).length / denominator * 100
              return <tr key={inspection.id} onClick={() => { setSelected(inspection); setInspection(inspection.id) }}>
                <td><b>{inspection.date}</b>{inspection.maintenance_event && <span className="repair-tag">Documented repair</span>}</td>
                <td>{inspection.hours.toLocaleString('es-CO')} h</td>
                <td><span className="inspector-chip">{inspection.inspector}</span></td>
                <td><div className="table-completeness"><span>{completeness.toFixed(0)}%</span><i><b style={{ width: completeness + '%' }} /></i></div></td>
                <td><div className="state-counts"><i className="legend-normal" />{count.normal}<i className="legend-alert" />{count.alert}<i className="legend-critical" />{count.critical}<i className="legend-incomplete" />{count.ni}</div></td>
                <td><div className="reading-chips">{measurements.map(m => <span key={m.point} title={m.point + ': ' + m.structural_state} className={'reading-chip reading-' + stateSlug(m.structural_state)}>{m.point.replace('SD-', '')}: {m.length_mm === null ? 'N/I' : m.length_mm + ' mm'}</span>)}</div></td>
                <td><button className="icon-button" title="Open inspection details" onClick={e => { e.stopPropagation(); setSelected(inspection); setInspection(inspection.id) }}><Eye size={15} /></button></td>
              </tr>
            })}
          </tbody></table></div>}
    </section>
    {showForm && <NewInspectionModal onClose={() => setShowForm(false)} onSaved={async id => { setShowForm(false); setInspection(id); await qc.invalidateQueries(); notify('success', 'Inspección guardada. El RAW histórico permanece sin cambios.') }} />}
    {selected && <InspectionDrawer inspection={selected} pointFilter={pointFilter} onClose={() => setSelected(null)} />}
  </>
}

function NewInspectionModal({ onClose, onSaved }: { onClose: () => void; onSaved: (id: number) => void }) {
  const qc = useQueryClient()
  const notify = useUI(s => s.notify)
  const rows = useQuery({ queryKey: ['inspections', 'new-form'], queryFn: () => api.inspections({ limit: 500 }) })
  const last = rows.data?.[0]
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [hours, setHours] = useState(last?.hours ? String(last.hours) : '')
  const [inspector, setInspector] = useState('')
  const [values, setValues] = useState<Record<string, string>>({ 'SD-01': '', 'SD-02': '', 'SD-03': '', 'SD-04': '' })
  const [missing, setMissing] = useState<Record<string, boolean>>({ 'SD-01': false, 'SD-02': false, 'SD-03': false, 'SD-04': false })
  const [comments, setComments] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const mutation = useMutation({ mutationFn: api.createInspection, onSuccess: r => onSaved(r.id), onError: e => setError(e.message) })
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    const blank = POINTS.find(point => !missing[point] && values[point].trim() === '')
    if (blank) { setError('Enter a measured length or mark ' + blank + ' as N/I. Blank fields are never converted to 0.'); return }
    const measurements = POINTS.map(point => ({ point, length_mm: missing[point] ? null : Number(values[point]), comment: comments[point] || null }))
    mutation.mutate({ equipment: 'EH4-01', date, hours: Number(hours), inspector, measurements })
  }
  return <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}><div className="modal-card inspection-modal">
    <div className="modal-head"><div><span className="eyebrow">INSPECTION ENTRY</span><h2>Register a new inspection</h2><p>All four points are required; mark N/I explicitly when not measured.</p></div><button className="icon-button" onClick={onClose}><X size={18} /></button></div>
    <form onSubmit={submit}>
      <div className="form-grid"><label>Inspection date<input required type="date" value={date} onChange={e => setDate(e.target.value)} /></label><label>Hour meter (h)<input required min="0" step="0.1" type="number" value={hours} onChange={e => setHours(e.target.value)} /><small>Last recorded: {last?.hours.toLocaleString('es-CO') ?? '—'} h</small></label><label className="form-wide">Inspector name / ID<input required maxLength={80} placeholder="e.g. INSP-04" value={inspector} onChange={e => setInspector(e.target.value)} /></label></div>
      <div className="form-section-label"><span>MEASUREMENTS</span><small>0 mm ≠ NULL / N/I</small></div>
      <div className="measurement-form-list">{POINTS.map((point, index) => <div className={'measurement-form-row ' + (missing[point] ? 'is-missing' : '')} key={point}>
        <div className="measurement-label"><b>{point}</b><span>{['Metal base de tijeras, lado derecho', 'Metal base de tijeras, lado izquierdo', 'Spindle delantero, lado derecho', 'Spindle delantero, lado izquierdo'][index]}</span></div>
        <label className="number-field"><input type="number" min="0" step="0.1" disabled={missing[point]} required={!missing[point]} value={values[point]} placeholder="0.0" onChange={e => setValues(v => ({ ...v, [point]: e.target.value }))} /><span>mm</span></label>
        <label className="ni-check"><input type="checkbox" checked={missing[point]} onChange={e => setMissing(v => ({ ...v, [point]: e.target.checked }))} /> N/I</label>
        <input className="comment-input" placeholder="Comment (optional)" value={comments[point] || ''} onChange={e => setComments(v => ({ ...v, [point]: e.target.value }))} />
      </div>)}</div>
      {error && <div className="form-error"><AlertTriangle size={15} />{error}</div>}
      <div className="modal-actions"><span><Camera size={14} /> Add photos after saving from Evidence.</span><button type="button" className="button button-ghost" onClick={onClose}>Cancel</button><button type="submit" className="button button-primary" disabled={mutation.isPending}><Save size={15} />{mutation.isPending ? 'Saving…' : 'Save inspection'}</button></div>
    </form>
  </div></div>
}

function InspectionDrawer({ inspection, pointFilter, onClose }: { inspection: Inspection; pointFilter: string; onClose: () => void }) {
  const setId = useUI(s => s.setInspection)
  const measurements = pointFilter === 'ALL' ? inspection.measurements : inspection.measurements.filter(m => m.point === pointFilter)
  return <div className="drawer-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}><aside className="detail-drawer">
    <div className="drawer-head"><div><span className="eyebrow">INSPECTION RECORD · {inspection.imported ? 'HISTORICAL RAW' : 'NEW RECORD'}</span><h2>{inspection.date}</h2><p>{inspection.hours.toLocaleString('es-CO')} h · {inspection.inspector}</p></div><button className="icon-button" onClick={onClose}><X size={18} /></button></div>
    <div className="drawer-section"><h3>{pointFilter === 'ALL' ? 'Four point readings' : 'Point reading · ' + pointFilter}</h3>{measurements.map(m => <MeasurementDetail key={m.point} m={m} historical={inspection.imported} />)}</div>
    <div className="drawer-section"><h3>Provenance</h3><div className="provenance-card"><b>{inspection.imported ? 'Imported from validated QA outputs' : 'Created in this application'}</b><span>{inspection.zone}</span><span>Equipment: {inspection.equipment}</span><span>{measurements.some(m => m.source_row) ? 'Excel source rows: ' + measurements.map(m => m.source_row).filter(Boolean).join(', ') : 'No original Excel row; this is an appended record.'}</span></div></div>
    <button className="button button-primary full-width" onClick={() => { setId(inspection.id); onClose() }}>Show in dashboard <ArrowRight size={15} /></button>
  </aside></div>
}

function MeasurementDetail({ m, historical }: { m: Measurement; historical: boolean }) {
  return <div className="drawer-measurement">
    <div className="measurement-source-copy">
      <b>{m.point}</b><span>{m.description}</span><small>{m.comment || 'No comment in source record.'}</small>
      <div className="measurement-source-facts"><span>Caution <b>{m.caution_mm} mm</b></span><span>Danger <b>{m.danger_mm} mm</b></span><span>ΔL RAW <b>{m.delta_l_raw === null ? 'N/D' : m.delta_l_raw + ' mm'}</b></span><span>Change <b>{m.change_class.replaceAll('_', ' ')}</b></span>{m.source_row !== null && <span className="source-row">Excel row <b>{m.source_row}</b></span>}</div>
      {m.data_warning && <small className="measurement-warning">Warning: {m.data_warning.replaceAll('_', ' ')}</small>}
      {historical && m.image_file && <div className="source-media-note"><span>Excel image reference: <b>{m.image_file}</b></span><small>Historical field photos were not supplied. The available Word image is a location drawing, not inspection-photo evidence.</small><a href={SD_SCHEME_URL} target="_blank" rel="noreferrer">Open official SD location drawing <ExternalLink size={12} /></a></div>}
    </div>
    <div className="measurement-value"><strong>{m.length_mm === null ? 'N/I' : m.length_mm + ' mm'}</strong><StatusBadge state={m.structural_state} /></div>
  </div>
}
