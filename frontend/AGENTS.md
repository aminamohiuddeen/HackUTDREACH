<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.

## What Lovable manages

Rules outside this block are the project's own. Change the pieces below in
Lovable, not by hand. With the [Lovable MCP](https://mcp.lovable.dev)
connected, `send_message` asks Lovable to do it; otherwise ask the user to
use the editor.

- **Database.** Do not add or edit `supabase/migrations/` or `drizzle/`.
  Ask Lovable to change the schema.
- **Generated files.** Do not edit a file whose header says it is automatically
  generated.
- **AI gateway.** Keep model calls on Lovable's gateway, and keep
  `LOVABLE_API_KEY` out of browser code.
- **Connectors.** Lovable provides native connectors. `list_connectors` shows
  which are enabled; `add_connector` only returns the dashboard link. When a
  connector is enabled, calls go through the connector gateway and need
  `LOVABLE_API_KEY`. When Lovable does not provide one, users can bring their
  own key and store it in Secrets.
- **Secrets.** Lovable manages them. Do not put secret values in the repo.
<!-- LOVABLE:END -->

## REACH frontend
- Domain types live in `src/lib/reach/types.ts`; all backend access goes through `src/lib/reach/api.ts` (demo mode when `VITE_REACH_API_BASE` is unset) — keeps FastAPI integration in one place.
- Backend payloads must be mapped in `adapt*` functions in api.ts; never assume undocumented fields.
- Demo classification rules mirror the backend in `src/lib/reach/classify.ts` (tested); app state is local via `ReachProvider` in `src/lib/reach/store.tsx`.
- Detection classification and sector coverage are separate state; verification actions must never modify sectors.
- All dashboard URLs live under the pathless `_authenticated` layout, including `/`; public auth and reset pages render outside the mission shell to prevent protected content flashes.
- Cloud owns authentication and a protected `user_roles` table only; roles are read server-side with the user's token, never from editable metadata, and FastAPI remains responsible for rescue data and token verification.
- Newly administrator-created/invited auth users receive the least-privilege first-responder role; administrator promotion is a trusted maintenance operation, never a browser write or automatic first-user promotion.
- Keep one root auth-state subscriber and scope the local ReachProvider to the authenticated user so logout clears cached and simulated mission state.
