import { useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiPost, setCsrfToken } from "@/lib/api";
import { queryClient } from "@/lib/queryClient";
import { BrandLogo } from "@/components/Brand";

interface Session { authenticated: boolean; setup_required?: boolean; csrf_token?: string }

// Calm fields: flat paper, a navy border and a soft amber halo on focus.
const field = "mt-2 w-full rounded-xl border border-slate-300 bg-white px-3.5 py-3 text-[15px] text-slate-950 outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-slate-400 focus:border-navy-600 focus:shadow-[0_0_0_4px_rgb(245_157_28/0.22)]";

export default function AuthGate({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const session = useQuery({ queryKey: ["auth"], queryFn: () => apiGet<Session>("/auth/session"), retry: false, refetchInterval: 60000 });
  const login = useMutation({
    mutationFn: () => apiPost<Session>(session.data?.setup_required ? "/auth/setup" : "/auth/login", { username, password }),
    onSuccess: (data) => {
      setPassword("");
      setCsrfToken(data.csrf_token ?? "");
      queryClient.removeQueries({ predicate: query => query.queryKey[0] !== "auth" });
      queryClient.setQueryData(["auth"], data);
    },
  });
  if (session.data?.authenticated) {
    setCsrfToken(session.data.csrf_token ?? "");
    return children;
  }
  const submit = (event: FormEvent) => { event.preventDefault(); login.mutate(); };
  return (
    <main className="relative grid min-h-screen overflow-hidden text-slate-900 lg:grid-cols-[1.05fr_1fr]">
      {/* Navy editorial panel */}
      <section className="auth-hero relative hidden flex-col justify-between overflow-hidden p-12 text-white xl:p-16 lg:flex">
        <div aria-hidden="true" className="pointer-events-none absolute -left-40 top-1/4 h-[520px] w-[520px] rounded-full bg-amber-500/20 blur-[130px]" />
        <div aria-hidden="true" className="pointer-events-none absolute -right-28 -top-28 h-[440px] w-[440px] rounded-full bg-sky-400/20 blur-[120px]" />
        <p className="relative flex items-center gap-3 text-[11px] font-semibold uppercase tracking-[0.24em] text-amber-300">
          <span className="h-0.5 w-8 rounded-full bg-amber-400" aria-hidden="true" />Two newsrooms · one editorial desk
        </p>
        <div className="relative max-w-xl">
          <h2 className="font-heading text-[3.1rem] font-semibold leading-[1.07] tracking-tight xl:text-[3.5rem]">
            Research deeply.<br />Write beautifully.<br /><span className="text-amber-400">Publish with care.</span>
          </h2>
          <div className="mt-10 grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-white/15 bg-white/[0.07] p-4 shadow-[inset_0_1px_0_rgb(255_255_255/0.12)] backdrop-blur-md">
              <div className="flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[0.18em] text-navy-200">
                <span className="h-2 w-2 rounded-full bg-violet-400" aria-hidden="true" />Kannada
              </div>
              <div className="mt-2 font-kannada text-lg leading-snug text-white">ಕನ್ನಡ ಆವೃತ್ತಿ</div>
              <div className="mt-0.5 text-xs text-navy-200">Kannada edition</div>
            </div>
            <div className="rounded-2xl border border-white/15 bg-white/[0.07] p-4 shadow-[inset_0_1px_0_rgb(255_255_255/0.12)] backdrop-blur-md">
              <div className="flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[0.18em] text-navy-200">
                <span className="h-2 w-2 rounded-full bg-cyan-300" aria-hidden="true" />English
              </div>
              <div className="mt-2 text-lg font-medium leading-snug text-white">English edition</div>
              <div className="mt-0.5 text-xs text-navy-200">Any English-reading audience</div>
            </div>
          </div>
        </div>
        <p className="relative text-xs text-navy-300">Runs locally on this computer. Your data and keys never leave it unless you publish.</p>
      </section>

      <section className="relative flex items-center justify-center p-5 sm:p-10">
        <div className="surface hairline-top w-full max-w-md rounded-3xl border border-slate-200 p-7 sm:p-10">
          <BrandLogo priority className="w-[min(100%,300px)]" />
          <p className="mt-8 text-[11px] font-semibold uppercase tracking-[0.22em] text-amber-700">Local desktop</p>
          <h1 className="mt-2 font-heading text-[28px] font-semibold leading-tight tracking-tight text-slate-950 sm:text-[30px]">{session.data?.setup_required ? "Create your administrator" : "Sign in to your newsroom"}</h1>
          <p className="mt-3 text-sm leading-relaxed text-slate-600">Review mode is on. Scheduling, paid AI calls and WordPress publishing are disabled.</p>
          {session.isPending ? <p className="mt-8 text-sm text-slate-600" role="status">Connecting to your local app…</p> : session.isError ?
            <div className="mt-8"><p role="alert" className="text-sm text-rose-800">The local server is unavailable.</p><button className="mt-3 text-sm font-medium text-navy-700 underline decoration-amber-400 underline-offset-4" onClick={() => session.refetch()}>Try again</button></div> :
            <form onSubmit={submit} className="mt-8 space-y-5">
              <label className="block text-[13px] font-medium text-slate-700">Username<input required autoComplete="username" aria-label="Username" value={username} onChange={e => setUsername(e.target.value)} pattern="[a-zA-Z0-9_.@\-]+" maxLength={80} className={field} /></label>
              <label className="block text-[13px] font-medium text-slate-700">Password<input required type="password" aria-label="Password" autoComplete={session.data?.setup_required ? "new-password" : "current-password"} minLength={session.data?.setup_required ? 12 : 1} maxLength={256} value={password} onChange={e => setPassword(e.target.value)} className={field} /></label>
              {session.data?.setup_required && <p className="text-xs text-slate-600">Choose at least 12 characters. This account is stored only in your local database.</p>}
              {login.isError && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{login.error.message}</p>}
              <button disabled={login.isPending} type="submit" className="w-full rounded-xl bg-gradient-to-b from-navy-700 to-navy-800 px-4 py-3 text-[15px] font-medium text-white shadow-[0_8px_20px_-10px_rgb(1_27_75/0.7),inset_0_1px_0_rgb(255_255_255/0.16)] transition-all duration-200 hover:from-navy-600 hover:to-navy-800 hover:shadow-[0_0_0_1px_rgb(245_157_28/0.7),0_12px_26px_-12px_rgb(1_27_75/0.75),inset_0_1px_0_rgb(255_255_255/0.2)] disabled:opacity-50">{login.isPending ? "Please wait…" : session.data?.setup_required ? "Create administrator" : "Sign in"}</button>
            </form>}
        </div>
      </section>
    </main>
  );
}
