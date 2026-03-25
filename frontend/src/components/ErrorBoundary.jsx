import { Component } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="flex flex-col items-center justify-center min-h-64 gap-4 p-8">
        <div className="w-12 h-12 rounded-full bg-bad/10 flex items-center justify-center">
          <AlertTriangle size={22} className="text-bad-light" />
        </div>
        <div className="text-center space-y-1">
          <p className="text-sm font-semibold text-ink-primary">Something went wrong</p>
          <p className="text-xs text-ink-muted max-w-sm">
            {this.state.error?.message || 'An unexpected error occurred rendering this page.'}
          </p>
        </div>
        <button
          onClick={() => this.setState({ hasError: false, error: null })}
          className="btn-ghost flex items-center gap-1.5 text-xs"
        >
          <RefreshCw size={12} /> Try again
        </button>
      </div>
    );
  }
}
