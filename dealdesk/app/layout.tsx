import type { Metadata } from "next";
import Link from "next/link";
import { cookies } from "next/headers";
import { verifySession } from "@/lib/auth";
import "./globals.css";

export const metadata: Metadata = { title: "Sinder Deal Desk", description: "Tenders, deals and market context for Sinder's team" };

const NAV = [["/", "Panel"], ["/today", "Today"], ["/tenders", "Tenders"], ["/tenders?country=USA&nosetaside=1", "USA"], ["/suppliers", "Suppliers"], ["/explore", "Explore"], ["/explore/israel", "Israel"], ["/explore/commodities", "Commodities"], ["/grants", "Grants"], ["/exempt", "No-tender buys"], ["/integrity", "Integrity"], ["/settings", "Status"]] as const;

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
            <div className="ml-auto text-xs text-[#9FBBDD]">{session ? session.email : ""}</div>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-5 py-6">{children}</main>
        <footer className="mx-auto max-w-6xl px-5 pb-8 text-xs text-muted">Internal tool. Data refreshes every 4 hours from official procurement sources; Israel daily.</footer>
      </body>
    </html>
  );
}
