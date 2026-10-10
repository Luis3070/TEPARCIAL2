import type { Inspection, Point } from '../types'
import { browserAudit, browserEvents, browserEvidence, browserInspections, browserOrders, createBrowserInspection, createBrowserOrder, overviewFor, pointsFor, recommendationFor, saveBrowserEvidence, snapshotFor, updateBrowserOrder } from './browserStore'

export const STATIC_DEMO = import.meta.env.VITE_STATIC_DEMO === 'true'
export const assetUrl = (path: string) => `${import.meta.env.BASE_URL}assets/${path}`

type DemoData = {
  health: unknown
  inspections: Inspection[]
  snapshots: unknown[]
  events: unknown[]
  qa: unknown
  maintenanceSummary: unknown
  inspectors: unknown[]
  model: unknown[]
  hotspots: unknown[]
  pointHistories: Record<string, unknown[]>
  overviews: Record<string, unknown>
  pointsByInspection: Record<string, unknown[]>
  recommendations: Record<string, unknown[]>
}

let source: Promise<DemoData> | undefined

function load(): Promise<DemoData> {
  source ??= fetch(`${import.meta.env.BASE_URL}demo/data.json`).then(response => {
    if (!response.ok) throw new Error('No se pudo cargar el historial de la demostración.')
    return response.json() as Promise<DemoData>
  })
  return source
}

export async function staticRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const data = await load()
  const url = new URL(path, 'https://demo.invalid')
  const route = url.pathname
  const added = browserInspections()
  const inspections = [...added, ...data.inspections].sort((a,b)=>b.date.localeCompare(a.date))
  const latestId = String(inspections[0]?.id ?? '')
  const selectedId = url.searchParams.get('inspection_id') || latestId
  const selected = inspections.find(row=>row.id===Number(selectedId))
  const method = init?.method?.toUpperCase() || 'GET'
  if(method==='POST'&&route==='/inspections')return createBrowserInspection(JSON.parse(String(init?.body)),data.inspections) as T
  if(method==='POST'&&route==='/work-orders')return createBrowserOrder(JSON.parse(String(init?.body)),inspections.flatMap(i=>i.measurements)) as T
  if(method==='PATCH'&&/^\/work-orders\/\d+$/.test(route))return updateBrowserOrder(Number(route.split('/')[2]),JSON.parse(String(init?.body))) as T
  if(method==='POST'&&route==='/evidence')return saveBrowserEvidence(init?.body as FormData,inspections,browserOrders()) as T
  if(method!=='GET')throw new Error(`Operación no disponible: ${method} ${route}`)
  let value: unknown

  if (route === '/health') value = {...(data.health as object),inspection_dates:inspections.length}
  else if (route === '/inspections') {
    let rows = inspections
    const start = url.searchParams.get('start')
    const end = url.searchParams.get('end')
    const point = url.searchParams.get('point')
    if (start) rows = rows.filter(row => row.date >= start)
    if (end) rows = rows.filter(row => row.date <= end)
    if (point) rows = rows.filter(row => row.measurements.some(m => m.point === point))
    const offset = Number(url.searchParams.get('offset') || 0)
    const limit = Number(url.searchParams.get('limit') || 100)
    value = rows.slice(offset, offset + limit)
  }
  else if (route.startsWith('/inspections/')) value = inspections.find(row => row.id === Number(route.split('/')[2]))
  else if (route === '/snapshots') value = [...data.snapshots,...added.map(snapshotFor)].sort((a:any,b:any)=>a.date.localeCompare(b.date))
  else if (route === '/points') value = data.pointsByInspection[selectedId] || (selected ? pointsFor(selected,data.pointsByInspection[String(data.inspections[0].id)] as Point[]) : undefined)
  else if (route.startsWith('/points/') && route.endsWith('/history')) {const code=route.split('/')[2];value=[...(data.pointHistories[code]||[]),...added.map(i=>{const m=i.measurements.find(x=>x.point===code);return m?{...m,date:i.date,hours:i.hours,inspector:i.inspector,equipment:i.equipment,maintenance_event_at_date:i.maintenance_event}:null}).filter(Boolean)].sort((a:any,b:any)=>a.date.localeCompare(b.date))}
  else if (route === '/maintenance/recommendations') value = data.recommendations[selectedId] || (selected ? recommendationFor(selected) : undefined)
  else if (route === '/maintenance/events') value = [...data.events,...browserEvents(added)].sort((a:any,b:any)=>a.date.localeCompare(b.date))
  else if (route === '/work-orders') {let rows=browserOrders();const status=url.searchParams.get('status'),point=url.searchParams.get('point');if(status)rows=rows.filter(r=>r.status===status);if(point)rows=rows.filter(r=>r.point===point);value=rows}
  else if (/^\/work-orders\/\d+\/history$/.test(route)) value = browserAudit(Number(route.split('/')[2]))
  else if (route === '/evidence') {let rows=browserEvidence();const point=url.searchParams.get('point'),inspection=url.searchParams.get('inspection_id'),order=url.searchParams.get('work_order_id');if(point)rows=rows.filter(r=>r.point===point);if(inspection)rows=rows.filter(r=>r.inspection_id===Number(inspection));if(order)rows=rows.filter(r=>r.work_order_id===Number(order));value=rows}
  else if (route === '/analytics/overview') value = data.overviews[selectedId] || (selected ? overviewFor(selected,data.overviews[String(data.inspections[0].id)]) : undefined)
  else if (route === '/analytics/qa') value = data.qa
  else if (route === '/analytics/maintenance-summary') value = data.maintenanceSummary
  else if (route === '/analytics/inspectors') value = [...data.inspectors,...added.map(i=>({date:i.date,hours:i.hours,inspector:i.inspector}))].sort((a:any,b:any)=>a.date.localeCompare(b.date))
  else if (route === '/3d/models') value = data.model
  else if (route === '/3d/hotspots') value = data.hotspots

  if (value === undefined) throw new Error(`Recurso de demostración no disponible: ${route}`)
  return value as T
}
