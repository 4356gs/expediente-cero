"use client";

export function LoadingState({ label = "Cargando expediente" }: { label?: string }) {
  return (
    <div className="statePanel" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <p>{label}…</p>
    </div>
  );
}

export function ErrorState({
  title = "No se pudo completar la operación",
  message,
  code,
  onRetry,
}: {
  title?: string;
  message: string;
  code?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="statePanel errorPanel" role="alert">
      <span className="stateIcon" aria-hidden="true">!</span>
      <div>
        <h2>{title}</h2>
        <p>{message}</p>
        {code ? <code>{code}</code> : null}
      </div>
      {onRetry ? <button className="button secondary" onClick={onRetry}>Reintentar</button> : null}
    </div>
  );
}

export function EmptyArtifact({ children }: { children: string }) {
  return <p className="emptyArtifact">{children}</p>;
}
