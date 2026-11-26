import { Component, type ErrorInfo, type ReactNode } from 'react'
import { reportError } from './Toast'

/** A crash while rendering must not leave a blank page: toast it and offer a way back. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(error: Error, _info: ErrorInfo) { reportError(error) }
  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="mt-24 flex flex-col items-center gap-3 text-center">
        <span className="msr !text-[40px] text-muted" aria-hidden>error</span>
        <div className="text-[20px] font-medium">Something went wrong</div>
        <p className="text-body text-[14px]">The details are in the notification. Reloading usually fixes it.</p>
        <button onClick={() => window.location.reload()} className="h-10 rounded-corgi border border-line bg-white px-4 text-sm cursor-pointer hover:bg-canvas">Reload</button>
      </div>
    )
  }
}
