import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MAKO Intelligence · Core 0.1",
  description: "Локальный каркас MAKO Intelligence — без рекламных данных и платных API.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
