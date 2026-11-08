import { useState, type FormEvent } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ArrowRight, Loader2 } from "lucide-react";
import { z } from "zod";
import { supabase } from "@/integrations/supabase/client";
import { AuthFrame } from "@/components/reach/auth-frame";
import { PasswordField } from "@/components/reach/password-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { approvedRole, authMessage } from "@/lib/auth/access";

export const Route = createFileRoute("/auth")({
  validateSearch: (s: Record<string, unknown>): { reason?: string | undefined } => ({ reason: typeof s["reason"] === "string" ? s["reason"] : undefined }),
  head: () => ({ meta: [{ title: "Sign In — REACH Mission Control" }, { name: "description", content: "Secure approved-personnel sign-in for REACH Mission Control." }, { property: "og:title", content: "Sign In — REACH Mission Control" }, { property: "og:description", content: "Secure access to REACH emergency operations." }, { property: "og:type", content: "website" }, { name: "twitter:card", content: "summary_large_image" }] }),
  component: SignIn,
});

function SignIn() {
  const navigate = useNavigate();
  const { reason } = Route.useSearch();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [recover, setRecover] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      const result = z.string().trim().email().max(254).safeParse(email);
      if (!result.success) { setError("Enter a valid email address."); return; }
      if (recover) {
        const { error: failure } = await supabase.auth.resetPasswordForEmail(result.data, { redirectTo: `${window.location.origin}/reset-password` });
        if (failure) throw failure;
        setSent(true); return;
      }
      const { data, error: failure } = await supabase.auth.signInWithPassword({ email: result.data, password });
      if (failure) throw failure;
      if (!data.user || !data.session) { setError("Your session could not be started. Please try again."); return; }
      const { data: roles, error: roleError } = await supabase.from("user_roles").select("role").eq("user_id", data.user.id);
      if (roleError || !approvedRole((roles ?? []).map((row) => row.role))) {
        await supabase.auth.signOut(); setError("This account has not been approved for REACH. Contact your administrator."); return;
      }
      await navigate({ to: "/", replace: true });
    } catch (failure) { setError(authMessage(failure)); } finally { setBusy(false); }
  }

  return <AuthFrame><section className="space-y-6"><h2 className="text-xl font-semibold">{recover ? "Recover your password" : "Sign in"}</h2>{reason === "expired" && !error && <p role="status" className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm text-warning">Your session has expired. Please sign in again.</p>}{reason === "unapproved" && !error && <p role="alert" className="text-sm text-destructive">Your account needs administrator approval.</p>}{sent ? <div className="space-y-4"><p role="status" className="text-base leading-relaxed">If this email belongs to an approved account, a password reset link is on its way. Check your inbox and spam folder.</p><Button variant="outline" onClick={() => { setSent(false); setRecover(false); }}>Back to sign in</Button></div> : <form onSubmit={submit} className="space-y-5" aria-busy={busy}><div className="space-y-2"><Label htmlFor="email">Email</Label><Input id="email" name="email" type="email" autoComplete="email" maxLength={254} required value={email} onChange={(event) => setEmail(event.target.value)} className="h-12 bg-card text-base" /></div>{!recover && <PasswordField value={password} onChange={setPassword} />}{error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</p>}<Button type="submit" disabled={busy} className="h-12 w-full text-base">{busy ? <Loader2 className="motion-safe:animate-spin" /> : <ArrowRight />}{busy ? "Please wait…" : recover ? "Send reset link" : "Sign In"}</Button><Button type="button" variant="link" className="h-11 px-0" disabled={busy} onClick={() => { setRecover(!recover); setError(""); }}>{recover ? "Back to sign in" : "Forgot Password?"}</Button></form>}<p className="border-t pt-5 text-sm text-muted-foreground">Access is by invitation. Contact your administrator for an account.</p></section></AuthFrame>;
}