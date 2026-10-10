import type { Inspection } from '../types'

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
  if (init?.method && init.method !== 'GET') {
    throw new Error('Esta publicación es de consulta. Los registros nuevos requieren la instalación con servidor.')
  }
  const data = await load()
  const url = new URL(path, 'https://demo.invalid')
  const route = url.pathname
  const latestId = String(data.inspections[0]?.id ?? '')
  const selectedId = url.searchParams.get('inspection_id') || latestId
  let value: unknown

  if (route === '/health') value = data.health
  else if (route === '/inspections') {
    let rows = data.inspections
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
  else if (route.startsWith('/inspections/')) value = data.inspections.find(row => row.id === Number(route.split('/')[2]))
  else if (route === '/snapshots') value = data.snapshots
  else if (route === '/points') value = data.pointsByInspection[selectedId]
  else if (route.startsWith('/points/') && route.endsWith('/history')) value = data.pointHistories[route.split('/')[2]]
  else if (route === '/maintenance/recommendations') value = data.recommendations[selectedId]
  else if (route === '/maintenance/events') value = data.events
  else if (route === '/work-orders' || route.startsWith('/work-orders/') || route === '/evidence') value = []
  else if (route === '/analytics/overview') value = data.overviews[selectedId]
  else if (route === '/analytics/qa') value = data.qa
  else if (route === '/analytics/maintenance-summary') value = data.maintenanceSummary
  else if (route === '/analytics/inspectors') value = data.inspectors
  else if (route === '/3d/models') value = data.model
  else if (route === '/3d/hotspots') value = data.hotspots

  if (value === undefined) throw new Error(`Recurso de demostración no disponible: ${route}`)
  return value as T
}
