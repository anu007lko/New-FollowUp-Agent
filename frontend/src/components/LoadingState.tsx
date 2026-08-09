interface LoadingStateProps {
  rows?: number;
  variant?: 'dashboard' | 'table' | 'record';
}

export function LoadingState({ rows = 6, variant = 'dashboard' }: LoadingStateProps) {
  if (variant === 'dashboard') {
    return (
      <div className="loading-state" aria-busy="true" aria-label="Loading dashboard">
        <div className="loading-greeting skeleton-shimmer" />
        <div className="loading-metrics">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="loading-card skeleton-shimmer" />
          ))}
        </div>
        <div className="loading-section skeleton-shimmer" />
      </div>
    );
  }

  if (variant === 'table') {
    return (
      <div className="loading-state" aria-busy="true" aria-label="Loading records">
        <div className="loading-toolbar skeleton-shimmer" />
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="loading-row skeleton-shimmer" />
        ))}
      </div>
    );
  }

  return (
    <div className="loading-state" aria-busy="true" aria-label="Loading record details">
      <div className="loading-record-header skeleton-shimmer" />
      <div className="loading-record-body skeleton-shimmer" />
      <div className="loading-record-timeline skeleton-shimmer" />
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-state" role="alert">
      <div className="error-state-icon">!</div>
      <h2 className="error-state-title">Unable to connect</h2>
      <p className="error-state-message">{message}</p>
      <p className="error-state-hint">Ensure the backend is running on 127.0.0.1:8000</p>
      {onRetry && (
        <button className="btn btn-primary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ icon, title, message }: { icon: string; title: string; message: string }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">{icon}</div>
      <h3 className="empty-state-title">{title}</h3>
      <p className="empty-state-message">{message}</p>
    </div>
  );
}
