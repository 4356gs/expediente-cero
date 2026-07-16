"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ErrorState, LoadingState } from "./status";
import { ApiError, listCases } from "@/lib/api";
import { formatDate, languageLabels, procedureLabels, statusLabels } from "@/lib/labels";
import type { CaseSummary } from "@/lib/types";

export function CaseQueue() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const load = useCallback(async () => {
    try {
      const result = await listCases();
      setError(null);
      setCases(result.items);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, "unexpected_error", "Error inesperado."));
    }
  }, []);
  useEffect(() => {
    let active = true;
    void listCases()
      .then((result) => {
        if (active) setCases(result.items);
      })
      .catch((caught: unknown) => {
        if (active) {
          setError(
            caught instanceof ApiError
              ? caught
              : new ApiError(0, "unexpected_error", "Error inesperado."),
          );
        }
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="pageShell">
      <section className="hero compactHero">
        <div>
          <p className="eyebrow">Mesa de revisión</p>
          <h1>Expedientes preparados para criterio humano</h1>
          <p>Revisa cada evidencia por separado y conserva la decisión profesional.</p>
        </div>
        <Link className="button primary" href="/cases/new">Nuevo expediente</Link>
      </section>
      {cases === null && !error ? <LoadingState label="Cargando expedientes" /> : null}
      {error ? <ErrorState message={error.message} code={error.code} onRetry={load} /> : null}
      {cases?.length === 0 ? (
        <section className="emptyQueue">
          <span className="stateIcon" aria-hidden="true">0</span>
          <h2>Aún no hay expedientes</h2>
          <p>Crea el primer caso sintético para iniciar el flujo.</p>
          <Link className="button primary" href="/cases/new">Crear expediente</Link>
        </section>
      ) : null}
      {cases && cases.length > 0 ? (
        <section className="queueCard" aria-labelledby="queue-title">
          <div className="sectionHeading">
            <div><p className="eyebrow">Bandeja</p><h2 id="queue-title">{cases.length} expedientes</h2></div>
            <button className="button ghost" onClick={load}>Actualizar</button>
          </div>
          <div className="tableWrap">
            <table>
              <thead><tr><th>Referencia</th><th>Procedimiento</th><th>Idioma</th><th>Estado</th><th>Actualizado</th><th><span className="srOnly">Abrir</span></th></tr></thead>
              <tbody>
                {cases.map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.reference}</strong></td>
                    <td>{procedureLabels[item.procedure_type]}</td>
                    <td>{languageLabels[item.output_language]}</td>
                    <td><span className={`statusBadge status-${item.status}`}>{statusLabels[item.status]}</span></td>
                    <td>{formatDate(item.updated_at)}</td>
                    <td><Link className="rowLink" href={`/cases/${item.id}`}>Revisar <span aria-hidden="true">→</span></Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  );
}
