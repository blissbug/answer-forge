import type { Metadata } from "next";
import "./globals.css";
import "./controls.css";

export const metadata: Metadata = {
  title: "AnswerForge · Evidence Workspace",
  description: "A focused workspace for evidence-aware questionnaire work.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
