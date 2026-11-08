import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function PasswordField({ id = "password", label = "Password", value, onChange, autoComplete = "current-password", minLength }: { id?: string; label?: string; value: string; onChange: (value: string) => void; autoComplete?: string; minLength?: number }) {
  const [visible, setVisible] = useState(false);
  return <div className="space-y-2"><Label htmlFor={id}>{label}</Label><div className="relative"><Input id={id} name={id} type={visible ? "text" : "password"} value={value} onChange={(event) => onChange(event.target.value)} autoComplete={autoComplete} required minLength={minLength} maxLength={128} className="h-12 bg-card pr-14 text-base" /><Button type="button" variant="ghost" size="icon" className="absolute right-1 top-1 h-10 w-10" aria-label={visible ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`} aria-pressed={visible} title={visible ? "Hide password" : "Show password"} onClick={() => setVisible(!visible)}>{visible ? <EyeOff /> : <Eye />}</Button></div></div>;
}