import type { Metadata } from "next";
import "./globals.css";
import { DebugNotesWidget } from "./debug-notes/DebugNotesWidget";

export const metadata: Metadata = {
  title: "Veridex",
  description: "Mobile-first Veridex client",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="shell">{children}</div>
        <DebugNotesWidget />
      </body>
    </html>
  );
}
