import { Suspense } from "react";
import type { Metadata, Viewport } from "next";
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

// Light-only design — pin both the tab-chrome color and the page's color
// scheme so dark-OS users still see a light browser bar. Next.js 15+
// requires themeColor/colorScheme under the `viewport` export, not
// `metadata`.
export const viewport: Viewport = {
  themeColor: "#fafbfc",
  colorScheme: "light",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${figtree.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* AppShell uses useSearchParams → must be wrapped in Suspense (Next.js 16). */}
        <Suspense fallback={<div className="min-h-dvh" />}>
          <AppShell>{children}</AppShell>
        </Suspense>
      </body>
    </html>
  );
}
