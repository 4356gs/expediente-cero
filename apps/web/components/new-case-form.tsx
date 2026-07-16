"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { ApiError, createCase } from "@/lib/api";
import { procedureLabels } from "@/lib/labels";
import type { OutputLanguage, ProcedureType } from "@/lib/types";

export function NewCaseForm() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [procedure, setProcedure] = useState<ProcedureType>("self_employed_registration");
  const [language, setLanguage] = useState<OutputLanguage>("es");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const data = new FormData(event.currentTarget);
    const documentType = String(data.get("document_type") ?? "").trim();
    const displayName = String(data.get("display_name") ?? "").trim();
    try {
      const created = await createCase({
        reference: String(data.get("reference")),
        procedure_type: procedure,
        output_language: language,
        is_synthetic: true,
        source_messages: [{ content: String(data.get("message")), is_synthetic: true }],
        documents: documentType && displayName
          ? [{ document_type: documentType, display_name: displayName, is_synthetic: true }]
          : [],
      });
      router.push(`/cases/${created.id}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, "unexpected_error", "Error inesperado."));
      setBusy(false);
    }
  }

  return (
    <div className="pageShell narrowShell">
      <nav className="breadcrumb" aria-label="Migas de pan"><Link href="/">Expedientes</Link><span aria-hidden="true">/</span><span>Nuevo</span></nav>
      <section className="formCard">
        <div className="sectionHeading"><div><p className="eyebrow">Intake sintético</p><h1>Crear expediente</h1></div><span className="syntheticFlag">Solo datos ficticios</span></div>
        <p className="lead">Registra una solicitud de demostración. No incluyas nombres, documentos ni datos reales.</p>
        {error ? <div className="inlineAlert" role="alert"><strong>{error.code}</strong><span>{error.message}</span></div> : null}
        <form onSubmit={submit} className="formGrid">
          <label className="field full"><span>Referencia</span><input name="reference" required minLength={1} maxLength={32} placeholder="EC-DEMO-001" /></label>
          <fieldset className="field full"><legend>Procedimiento</legend><div className="choiceGrid">
            {(Object.entries(procedureLabels) as Array<[ProcedureType, string]>).map(([value, label]) => (
              <label className={`choiceCard ${procedure === value ? "selected" : ""}`} key={value}><input type="radio" name="procedure" value={value} checked={procedure === value} onChange={() => setProcedure(value)} /><span>{label}</span></label>
            ))}
          </div></fieldset>
          <fieldset className="field full"><legend>Idioma de salida</legend><div className="segmented">
            <label><input type="radio" name="language" value="es" checked={language === "es"} onChange={() => setLanguage("es")} /><span>Español</span></label>
            <label><input type="radio" name="language" value="gl" checked={language === "gl"} onChange={() => setLanguage("gl")} /><span>Galego</span></label>
          </div></fieldset>
          <label className="field full"><span>Mensaje fuente sintético</span><textarea name="message" required minLength={1} maxLength={8000} rows={7} placeholder="Describe la solicitud ficticia tal como llegaría a la gestoría…" /></label>
          <div className="field full subSection"><span>Documento sintético opcional</span><p>Solo metadatos; no se cargan archivos.</p></div>
          <label className="field"><span>Tipo</span><input name="document_type" maxLength={64} placeholder="identity" /></label>
          <label className="field"><span>Nombre visible</span><input name="display_name" maxLength={255} placeholder="Identidad sintética.pdf" /></label>
          <div className="formActions full"><Link className="button secondary" href="/">Cancelar</Link><button className="button primary" disabled={busy} type="submit">{busy ? "Creando…" : "Crear expediente"}</button></div>
        </form>
      </section>
    </div>
  );
}
