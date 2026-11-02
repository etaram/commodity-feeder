"use client";
import { useEffect } from "react";
import { usePathname, useSearchParams } from "next/navigation";

// Classic screens: report each page the signed-in user opens to the activity log (admin view in the panel).
export default function Track() {
  const path = usePathname();
  const q = useSearchParams()?.toString() || "";
  useEffect(() => {
    if (!path || path === "/login") return;
    fetch("/api/activity", { method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true, body: JSON.stringify({ action: "view", target: "page " + path, detail: q.slice(0, 300) }) }).catch(() => {});
  }, [path, q]);
  return null;
}
