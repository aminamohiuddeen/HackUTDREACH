import type { ReactNode } from "react";
import { Radio, ShieldCheck } from "lucide-react";

export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-svh flex-col bg-background">
      <header className="flex items-center gap-3 border-b bg-card px-6 py-5 sm:px-10">
        <span className="flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground"><Radio aria-hidden className="h-5 w-5" /></span>
        <div><div className="font-display text-2xl font-bold">REACH</div><div className="text-sm text-muted-foreground">Mission Control</div></div>
      </header>
      <main className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-md space-y-9 motion-safe:animate-in motion-safe:fade-in motion-safe:duration-500">
          <div className="space-y-3"><div className="flex items-center gap-2 text-sm font-medium text-primary"><ShieldCheck aria-hidden className="h-4 w-4" />Authorized personnel</div><h1 className="font-display text-4xl font-semibold">REACH Mission Control</h1><p className="text-base leading-relaxed text-muted-foreground">Find the forgotten. Reach the unreachable.</p></div>
          {children}
        </div>
      </main>
      <footer className="border-t px-6 py-5 text-center text-sm text-muted-foreground">Rescue · Evaluation · Assistance · Coordination · Hope</footer>
    </div>
  );
}