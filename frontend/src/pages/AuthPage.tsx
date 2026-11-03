import { useState } from "react";
import { Navigate } from "react-router";
import { toast } from "sonner";
import { Button, Input, Logo } from "@/components/ui";
import { useAuth } from "@/store/auth";

export function AuthPage() {
  const { config, user, signin, signup } = useAuth();
  const onboarding = !!config?.onboarding;
  const signupEnabled = !!config?.features.enable_signup;
  const [mode, setMode] = useState<"signin" | "signup">(onboarding ? "signup" : "signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;
  const isSignup = onboarding || mode === "signup";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (isSignup) await signup(name, email, password);
      else await signin(email, password);
    } catch (err: any) {
      toast.error(err.message ?? "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative flex min-h-full items-center justify-center overflow-hidden bg-white px-4 py-10 dark:bg-gray-950">
      <div className="pointer-events-none absolute -top-40 left-1/2 h-96 w-[44rem] -translate-x-1/2 rounded-full bg-accent-500/15 blur-3xl" />
      <div className="relative w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo className="mb-4 size-12" />
          <h1 className="text-2xl font-semibold">
            {onboarding ? `Welcome to ${config?.name ?? "Open Cowork"}` : isSignup ? "Create your account" : `Sign in to ${config?.name ?? "Open Cowork"}`}
          </h1>
          <p className="mt-2 text-sm text-gray-500">
            {onboarding
              ? "Create the first account to get started. It becomes the administrator."
              : isSignup
                ? "New accounts may need to be activated by an admin."
                : "Chat with local models and get work done with Cowork."}
          </p>
        </div>

        <form onSubmit={submit} className="space-y-3">
          {isSignup && (
            <Input required autoFocus placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
          )}
          <Input
            required
            autoFocus={!isSignup}
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
          />
          <Input
            required
            type="password"
            placeholder="Password"
            minLength={isSignup ? 8 : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={isSignup ? "new-password" : "current-password"}
          />
          <Button type="submit" variant="primary" loading={busy} className="w-full py-2.5">
            {onboarding ? "Create admin account" : isSignup ? "Create account" : "Sign in"}
          </Button>
        </form>

        {!onboarding && (
          <div className="mt-6 text-center text-sm text-gray-500">
            {mode === "signin" ? (
              signupEnabled ? (
                <>
                  Don't have an account?{" "}
                  <button className="font-medium text-gray-900 hover:underline dark:text-gray-100" onClick={() => setMode("signup")}>
                    Sign up
                  </button>
                </>
              ) : (
                "New sign-ups are disabled. Ask an admin for an account."
              )
            ) : (
              <>
                Already have an account?{" "}
                <button className="font-medium text-gray-900 hover:underline dark:text-gray-100" onClick={() => setMode("signin")}>
                  Sign in
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function PendingPage() {
  const { user, signout, refreshUser } = useAuth();
  const [checking, setChecking] = useState(false);
  return (
    <div className="flex min-h-full items-center justify-center px-4">
      <div className="max-w-md text-center">
        <Logo className="mx-auto mb-5 size-12" />
        <h1 className="text-2xl font-semibold">Account activation pending</h1>
        <p className="mt-3 text-gray-500">
          Hi {user?.name}, your account has been created. An administrator needs to activate it before you can start
          using the app.
        </p>
        <div className="mt-6 flex justify-center gap-2">
          <Button
            variant="primary"
            loading={checking}
            onClick={async () => {
              setChecking(true);
              try {
                await refreshUser();
              } finally {
                setChecking(false);
              }
            }}
          >
            Check again
          </Button>
          <Button variant="ghost" onClick={signout}>
            Sign out
          </Button>
        </div>
      </div>
    </div>
  );
}
