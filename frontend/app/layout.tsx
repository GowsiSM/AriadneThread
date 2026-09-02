import type { Metadata } from "next";
import "./globals.css";
import ThemeProvider from "@/lib/ThemeProvider";

export const metadata: Metadata = {
  title: "Fraud Ring Sentinel",
  description: "Real-time, defense-only fraud-ring detection with fairness-audited alerts.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-bg text-fg antialiased">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
