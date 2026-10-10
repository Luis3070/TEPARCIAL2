import type { Evidence, Inspection, MaintenanceEvent, Point, Recommendation, Snapshot, WorkOrder } from '../types'
import { STATIC_DEMO, staticRequest } from './staticDemo'
import { browserEvidenceUrl } from './browserStore'

const BASE = import.meta.env.VITE_API_BASE || (import.meta.env.PROD ? '/api' : 'http://127.0.0.1:8000/api')
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (STATIC_DEMO) return staticRequest<T>(path, init)
  const response = await fetch(`${BASE}${path}`, init)
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try { const body = await response.json(); detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail) } catch { /* keep status */ }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}
const query = (values: Record<string, string | number | undefined>) => {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([k,v]) => { if (v !== undefined) params.set(k, String(v)) })
  return params.size ? `?${params.toString()}` : ''
}
export const api = {
  health: () => request<{status:string;inspection_dates:number}>('/health'),
  overview: (id?:number) => request<any>(`/analytics/overview${query({inspection_id:id})}`),
  inspections: (opts:Record<string,string|number|undefined>={}) => request<Inspection[]>(`/inspections${query(opts)}`),
  inspection: (id:number) => request<Inspection>(`/inspections/${id}`),
  createInspection: (body:unknown) => request<Inspection>('/inspections',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  snapshots: () => request<Snapshot[]>('/snapshots'),
  points: (id?:number) => request<Point[]>(`/points${query({inspection_id:id})}`),
  pointHistory: (point:string) => request<any[]>(`/points/${point}/history`),
  recommendations: (id?:number) => request<Recommendation[]>(`/maintenance/recommendations${query({inspection_id:id})}`),
  events: () => request<MaintenanceEvent[]>('/maintenance/events'),
  workOrders: (opts:Record<string,string|undefined>={}) => request<WorkOrder[]>(`/work-orders${query(opts)}`),
  workOrderHistory: (id:number) => request<any[]>(`/work-orders/${id}/history`),
  createWorkOrder: (body:unknown) => request<WorkOrder>('/work-orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  updateWorkOrder: (id:number,body:unknown) => request<WorkOrder>(`/work-orders/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  evidence: (opts:Record<string,string|number|undefined>={}) => request<Evidence[]>(`/evidence${query(opts)}`),
  uploadEvidence: (body:FormData) => request<Evidence>('/evidence',{method:'POST',body}),
  qa: () => request<any>('/analytics/qa'),
  maintenanceSummary: () => request<any>('/analytics/maintenance-summary'),
  inspectors: () => request<any[]>('/analytics/inspectors'),
  model: () => request<any[]>('/3d/models'),
  hotspots: () => request<any[]>('/3d/hotspots'),
  saveHotspot: (code:string,body:unknown) => request<any>(`/3d/hotspots/${code}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  evidenceUrl: (id:number) => `${BASE}/evidence/${id}`,
  evidenceFileUrl: (id:number) => STATIC_DEMO ? browserEvidenceUrl(id) : Promise.resolve(`${BASE}/evidence/${id}`),
}
