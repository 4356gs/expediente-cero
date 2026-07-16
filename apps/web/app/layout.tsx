import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Expediente Cero",
  description: "Revisión humana de expedientes sintéticos asistidos por IA",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="es">
      <body>
        <header className="siteHeader">
          <Link className="brand" href="/" aria-label="Expediente Cero, inicio">
            <span className="brandMark" aria-hidden="true">EC</span>
            <span>
              <strong>Expediente Cero</strong>
              <small>Revisión profesional asistida</small>
            </span>
          </Link>
          <span className="syntheticFlag">Entorno sintético</span>
        </header>
        <main>{children}</main>
        <footer className="siteFooter">
          Preparación de intake · Sin asesoría ni presentación ante organismos
        </footer>
      </body>
    </html>
  );
}
