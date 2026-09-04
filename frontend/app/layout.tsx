import type { Metadata } from "next";
import { Geist,Geist_Mono } from "next/font/google";
import "./globals.css";
const sans=Geist({variable:"--font-sans",subsets:["latin"]}); const mono=Geist_Mono({variable:"--font-mono",subsets:["latin"]});
export const metadata:Metadata={title:"Vector — Agentic Trading Desk",description:"Paper trading control room for a multi-agent strategy, risk, and execution system."};
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){return <html lang="en"><body className={`${sans.variable} ${mono.variable}`}>{children}</body></html>}
