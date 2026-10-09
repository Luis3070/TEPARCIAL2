import { Activity } from 'lucide-react'
export function EmptyState({title='Sin datos',description='No hay registros para los filtros seleccionados.'}:{title?:string;description?:string}) {
 return <div className="empty-state"><Activity size={22}/><strong>{title}</strong><span>{description}</span></div>
}
