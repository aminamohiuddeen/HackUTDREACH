CREATE TYPE public.app_role AS ENUM ('administrator', 'first_responder');
CREATE TABLE public.user_roles (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 role public.app_role NOT NULL,
 UNIQUE(user_id, role)
);
GRANT SELECT ON public.user_roles TO authenticated;
GRANT ALL ON public.user_roles TO service_role;
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users read their own approved roles" ON public.user_roles FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE FUNCTION public.has_role(_user_id uuid, _role public.app_role) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$ SELECT EXISTS (SELECT 1 FROM public.user_roles WHERE user_id = _user_id AND role = _role) $$;
REVOKE ALL ON FUNCTION public.has_role(uuid, public.app_role) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO authenticated, service_role;
CREATE FUNCTION public.assign_approved_responder_role() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$ BEGIN INSERT INTO public.user_roles(user_id, role) VALUES (NEW.id, 'first_responder'); RETURN NEW; END; $$;
REVOKE ALL ON FUNCTION public.assign_approved_responder_role() FROM PUBLIC, anon, authenticated;
CREATE TRIGGER assign_approved_responder_role AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.assign_approved_responder_role();
INSERT INTO public.user_roles(user_id, role) SELECT id, 'first_responder'::public.app_role FROM auth.users ON CONFLICT DO NOTHING;