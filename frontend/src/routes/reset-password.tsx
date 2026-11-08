import { useEffect, useState, type FormEvent } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { AuthFrame } from "@/components/reach/auth-frame";
import { PasswordField } from "@/components/reach/password-field";
import { Button } from "@/components/ui/button";
import { authMessage } from "@/lib/auth/access";

export const Route = createFileRoute("/reset-password")({
  head: () => ({ meta: [{ title: "Reset Password — REACH Mission Control" }, { name: "description", content: "Set a new password using your secure REACH recovery or invitation link." }, { property: "og:title", content: "Reset Password — REACH Mission Control" }, { property: "og:description", content: "Secure account recovery for REACH personnel." }, { property: "og:type", content: "website" }, { name: "twitter:card", content: "summary_large_image" }] }),
  component: ResetPassword,
});

function ResetPassword() {
  const [ready, setReady] = useState(false);
  const [checking, setChecking] = useState(true);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  useEffect(() => {
    let active = true;
    const type = new URLSearchParams(window.location.hash.slice(1)).get("type");
    const eligible = type === "recovery" || type === "invite";
    const check = async () => {
      const { data, error: failure } = await supabase.auth.getUser();
      if (!active) return;
      setReady(eligible && !failure && !!data.user); setChecking(false);
    };
    void check();
    return () => { active = false; };
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError("");
    if (password.length < 12 || password.length > 128) { setError("Use between 12 and 128 characters."); return; }
    if (password !== confirm) { setError("The passwords do not match."); return; }
    setBusy(true);
    try {
      const { error: failure } = await supabase.auth.updateUser({ password });
      if (failure) throw failure;
      await supabase.auth.signOut(); setDone(true);
    } catch (failure) { setError(authMessage(failure)); } finally { setBusy(false); }
  }
  return <AuthFrame><section className="space-y-5"><h2 className="text-xl font-semibold">Set your password</h2>{checking ? <p role="status" className="flex items-center gap-2"><Loader2 className="h-4 w-4 motion-safe:animate-spin" />Verifying your link…</p> : done ? <><p role="status">Your password has been updated. Sign in with your new password.</p><Button asChild><Link to="/auth">Return to sign in</Link></Button></> : !ready ? <><p role="alert" className="text-destructive">This link is invalid or has expired. Request a new password reset link.</p><Button asChild variant="outline"><Link to="/auth">Back to sign in</Link></Button></> : <form onSubmit={submit} className="space-y-5" aria-busy={busy}><PasswordField label="New password" autoComplete="new-password" minLength={12} value={password} onChange={setPassword} /><p className="text-sm text-muted-foreground">Use at least 12 characters.</p><PasswordField id="confirm-password" label="Confirm password" autoComplete="new-password" minLength={12} value={confirm} onChange={setConfirm} />{error && <p role="alert" className="text-sm text-destructive">{error}</p>}<Button type="submit" disabled={busy} className="h-12 w-full">{busy && <Loader2 className="motion-safe:animate-spin" />}{busy ? "Updating…" : "Update password"}</Button></form>}</section></AuthFrame>;
}