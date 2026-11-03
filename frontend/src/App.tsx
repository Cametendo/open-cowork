import { useEffect } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router";
import { Toaster } from "sonner";
import { useApp } from "@/store/app";
import { useAuth } from "@/store/auth";
import { Sidebar } from "@/components/Sidebar";
import { SettingsModal } from "@/components/SettingsModal";
import { Logo, Spinner } from "@/components/ui";
import { AdminPage } from "@/pages/AdminPage";
import { AuthPage, PendingPage } from "@/pages/AuthPage";
import { ChatPage } from "@/pages/ChatPage";
import { CoworkRoutes } from "@/pages/CoworkPage";

function AppLayout() {
  const { user, config } = useAuth();
  const loadModels = useApp((s) => s.loadModels);
  const location = useLocation();

  useEffect(() => {
    if (user && user.role !== "pending") loadModels();
  }, [user, loadModels]);

  if (!user) return <Navigate to="/auth" replace state={{ from: location.pathname }} />;
  if (user.role === "pending") return <PendingPage />;
  if (location.pathname.startsWith("/admin") && user.role !== "admin") return <Navigate to="/" replace />;
  if (location.pathname.startsWith("/cowork") && user.role !== "admin" && config && !config.features.cowork) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar />
      <main className="flex h-full min-w-0 flex-1">
        <Outlet />
      </main>
      <SettingsModal />
    </div>
  );
}

export default function App() {
  const { ready, init, theme } = useAuth();

  useEffect(() => {
    init();
  }, [init]);

  const toaster = (
    <Toaster
      position="top-center"
      theme={theme === "system" ? "system" : theme}
      toastOptions={{ className: "!rounded-2xl" }}
    />
  );

  if (!ready) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <Logo className="size-10 animate-pulse" />
        <Spinner className="text-gray-400" />
      </div>
    );
  }

  return (
    <>
      {toaster}
      <Routes>
        <Route path="/auth" element={<AuthPage />} />
        <Route element={<AppLayout />}>
          <Route path="/" element={<ChatPage />} />
          <Route path="/c/:id" element={<ChatPage />} />
          <Route path="/cowork/*" element={<CoworkRoutes />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/admin/:tab" element={<AdminPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </>
  );
}
