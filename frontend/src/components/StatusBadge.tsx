import { stateSlug, type StructuralState } from '../types'
export function StatusBadge({state}:{state:StructuralState|string}) {
  const label = state === 'N/I' ? 'No inspeccionado' : state
  return <span className={`status-badge state-${stateSlug(state)}`}><i />{label}</span>
}
export function PriorityBadge({priority}:{priority:string|null}) { return <span className={`priority-badge ${priority ? `priority-${priority.toLowerCase()}` : 'priority-na'}`}>{priority || '—'}</span> }
