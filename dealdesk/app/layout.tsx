import type { Metadata } from "next";
import Link from "next/link";
import { cookies } from "next/headers";
import { verifySession } from "@/lib/auth";
import SignOut from "@/components/SignOut";
import Track from "@/components/Track";
import { Suspense } from "react";
import "./globals.css";

export const metadata: Metadata = { title: "Sinder Deal Desk", description: "Tenders, deals and market context for Sinder's team" };

const NAV = [["/", "Panel"], ["/today", "Today"], ["/tenders", "Tenders"], ["/tenders?country=USA&nosetaside=1", "USA"], ["/suppliers", "Suppliers"], ["/clients", "Clients"], ["/explore", "Explore"], ["/explore/israel", "Israel"], ["/prices", "Prices"], ["/explore/commodities", "Trends"], ["/grants", "Grants"], ["/exempt", "No-tender buys"], ["/integrity", "Integrity"], ["/settings", "Status"]] as const;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const jar = await cookies();
  const session = verifySession(jar.get("dd_session")?.value);
  return (
    <html lang="en">
      <body>
        <header className="bg-navy text-white">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-5 py-3">
            <Link href="/today" className="text-lg font-bold tracking-tight">Sinder <span className="text-[#9FBBDD] font-semibold">Deal Desk</span></Link>
            {session && (
              <nav className="flex flex-wrap gap-4 text-sm text-[#C9D6E6]">
                {NAV.map(([href, label]) => (<a key={href} href={href} className="hover:text-white">{label}</a>))}
              </nav>
            )}
            {session && (
              <div className="ml-auto flex items-center gap-3 text-xs text-[#9FBBDD]">
                <span>{session.name || session.email} <span className="rounded bg-[#2B4A72] px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-white">{session.role}</span></span>
                {session.role === "admin" && <a href="/#users" className="hover:text-white">Users</a>}
                <SignOut />
              </div>
            )}
          </div>
        </header>
        {session && <Suspense fallback={null}><Track /></Suspense>}
        <main className="mx-auto max-w-6xl px-5 py-6">{children}</main>
        <footer className="mx-auto max-w-6xl px-5 pb-8 text-xs text-muted">Internal tool. Data refreshes every 4 hours from official procurement sources; Israel daily.</footer>
      </body>
    </html>
  );
}
