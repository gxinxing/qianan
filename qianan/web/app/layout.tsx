import type { Metadata } from "next";
import { Space_Grotesk, IBM_Plex_Mono } from "next/font/google";
import { AuthProvider } from "@/components/AuthProvider";
import { MotionProvider } from "@/components/MotionUI";
import "./globals.css";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "千岸 QianAn · 一稿多岸",
  description: "一个设计稿，铺到千片海岸 —— 多平台智能上新 Agent",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className={`${spaceGrotesk.variable} ${plexMono.variable}`}>
      <body className="min-h-screen font-sans antialiased">
        <MotionProvider><AuthProvider>{children}</AuthProvider></MotionProvider>
      </body>
    </html>
  );
}
