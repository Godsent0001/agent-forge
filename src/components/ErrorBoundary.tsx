import { Component, type ErrorInfo, type ReactNode } from "react";

type ErrorBoundaryProps = {
  children: ReactNode;
};

type ErrorBoundaryState = {
  hasError: boolean;
  message: string | null;
};

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    hasError: false,
    message: null,
  };

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    return {
      hasError: true,
      message: error instanceof Error ? error.message : "Unknown renderer error",
    };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("AgentForge renderer error", error, info.componentStack);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="h-screen w-screen flex items-center justify-center bg-surface-950 p-6">
        <div className="w-full max-w-lg rounded-panel border border-red-200 bg-white p-6 shadow-card">
          <h1 className="text-lg font-bold text-status-error">AgentForge UI failed to render</h1>
          <p className="mt-2 text-sm text-slate-600">
            The renderer hit an unexpected error. Restart the app after checking the error details.
          </p>
          <pre className="mt-4 max-h-40 overflow-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-600 whitespace-pre-wrap">
            {this.state.message}
          </pre>
        </div>
      </div>
    );
  }
}
