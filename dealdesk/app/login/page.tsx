import LoginForm from "./LoginForm";

export const dynamic = "force-dynamic";

export default async function Login({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const p = await searchParams;
  const notice = p.pending ? "pending" : p.disabled ? "disabled" : p.err === "google" ? "google" : "";
  return <LoginForm google={Boolean(process.env.GOOGLE_CLIENT_ID)} notice={notice} />;
}
