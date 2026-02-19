import type { Metadata } from "next";

import { ThemeProvider } from "@/components/theme-provider";
import { Toaster } from "@/components/ui/sonner";
import { DEFAULT_THEME } from "@/lib/theme-palettes";

import "./globals.css";

export const metadata: Metadata = {
  title: "Leave Tracker",
  description: "Leave management frontend powered by shadcn/ui and Next.js",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">
        <ThemeProvider
          attribute="data-theme"
          defaultTheme={DEFAULT_THEME}
          enableSystem={false}
          storageKey="leave-tracker-theme"
        >
          {children}
          <Toaster richColors />
        </ThemeProvider>
      </body>
    </html>
  );
}
