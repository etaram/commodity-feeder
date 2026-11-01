"use client";

export default function SignOut() {
  return (
    <button onClick={async () => { await fetch("/api/logout", { method: "POST" }); window.location.href = "/login"; }} className="rounded border border-[#4A6A94] px-2 py-0.5 text-xs text-[#C9D6E6] hover:bg-[#2B4A72]">
      Sign out
    </button>
  );
}
