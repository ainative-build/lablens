import { Suspense } from "react";
import type { Metadata } from "next";
import { Figtree, Geist, Geist_Mono } from "next/font/google";
import { AppShell } from "@/components/app-shell";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Figtree — healthcare-warm display face for headings + brand voice. Pairs
// with Geist Sans on body. Loaded with display=swap; reserves layout space.
const figtree = Figtree({
  variable: "--font-figtree",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "LabLens — Understand your lab report in plain English",
  description:
    "Upload a PDF, get a clear breakdown of what's normal, what's worth following up, and what to ask your doctor — in seconds.",
};

/* Inline theme bootstrap — runs synchronously in <head> before paint so we
   never flash the wrong theme. Order: localStorage > prefers-color-scheme. */
const THEME_INIT_SCRIPT = `(function(){try{var s=localStorage.getItem("lablens.theme");var sys=window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";var t=(s==="dark"||s==="light")?s:sys;document.documentElement.dataset.theme=t;}catch(e){document.documentElement.dataset.theme="light";}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      // Theme is set client-side by the inline script below; suppress the
      // hydration warning since the server can't know the user's choice.
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} ${figtree.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* Theme bootstrap — first body child so it runs before React
            hydrates. Putting it in <head> doesn't work in Next.js 16 App
            Router (the framework manages <head> itself and strips
            children). Synchronous script keeps data-theme set pre-paint
            so we never flash the wrong theme. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        {/* AppShell uses useSearchParams → must be wrapped in Suspense (Next.js 16). */}
        <Suspense fallback={<div className="min-h-dvh" />}>
          <AppShell>{children}</AppShell>
        </Suspense>
      </body>
    </html>
  );
}
