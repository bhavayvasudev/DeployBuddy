import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Deploy Buddy · Dry-run requests",
  description: "Validate, review and explicitly confirm a local dry-run deployment plan.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
