import { createServerFn } from "@tanstack/react-start";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";
import { approvedRole } from "./access";

export const getApprovedAccount = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    const { data, error } = await context.supabase.from("user_roles").select("role").eq("user_id", context.userId);
    if (error) throw new Error("Unable to verify account access.");
    const role = approvedRole(data.map((row) => row.role));
    if (!role) throw new Error("This account has not been approved for REACH.");
    return { userId: context.userId, role };
  });