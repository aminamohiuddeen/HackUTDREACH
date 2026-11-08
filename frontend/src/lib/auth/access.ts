export type ReachRole = "administrator" | "first_responder";

export function approvedRole(roles: readonly string[]): ReachRole | null {
  if (roles.includes("administrator")) return "administrator";
  if (roles.includes("first_responder")) return "first_responder";
  return null;
}

export function authMessage(error: unknown): string {
  const code = typeof error === "object" && error !== null && "code" in error ? String(error.code) : "";
  if (code === "invalid_credentials") return "Email or password is incorrect.";
  if (code === "email_not_confirmed") return "Your account is not confirmed. Contact your administrator.";
  if (code === "over_request_rate_limit" || code === "over_email_send_rate_limit") return "Too many attempts. Please wait before trying again.";
  if (code === "weak_password") return "Choose a stronger password that has not appeared in a data breach.";
  if (code === "same_password") return "Choose a password different from your current password.";
  if (code === "otp_expired" || code === "session_not_found" || code === "refresh_token_not_found") return "Your session or link has expired. Please sign in or request a new reset link.";
  return "Unable to complete this request. Check your connection and try again.";
}