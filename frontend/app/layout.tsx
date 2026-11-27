import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MAKO Intelligence · Рабочее пространство",
  description: "Локальный кабинет MAKO Intelligence — без реальных рекламных данных.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
