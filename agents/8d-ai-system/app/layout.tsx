import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "8D AI — Root Cause Analysis System",
  description: "Agentic AI-powered 8D Problem Solving & Corrective Action Management",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 antialiased">{children}</body>
    </html>
  );
}
