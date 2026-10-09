import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

type Props = { children: ReactNode; fallback?: ReactNode }
type State = { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Dashboard render error:', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return this.props.fallback ?? (
        <section className="fatal-error" role="alert">
          <AlertTriangle size={22} />
          <div>
            <b>No se pudo mostrar esta sección</b>
            <span>{this.state.error.message || 'Error inesperado al iniciar la interfaz.'}</span>
            <small>Recarga la página. Si continúa, comparte este mensaje con soporte.</small>
          </div>
        </section>
      )
    }
    return this.props.children
  }
}
