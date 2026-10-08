import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "NeuroResect · Connectome research workstation",
  description:
    "Explore structural brain networks, simulate virtual resections, and compare reproducible research experiments. Synthetic research demonstration.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
