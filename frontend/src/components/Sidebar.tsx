import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import {
  Bot,
  FolderGit2,
  LogOut,
  MessageSquare,
  MoreHorizontal,
  PanelLeftClose,
  Pencil,
  Pin,
  PinOff,
  Search,
  Settings,
  Shield,
  SquarePen,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn, groupByDate } from "@/lib/utils";
import { useApp } from "@/store/app";
import { useAuth } from "@/store/auth";
import { Avatar, ConfirmDialog, IconButton, Logo, Menu, MenuItem } from "./ui";

interface Item {
  id: string;
  title: string;
  updated_at: number;
  pinned?: boolean;
  status?: string;
  subtitle?: string | null;
}

function ItemRow({
  item,
  href,
  active,
  onRename,
  onDelete,
  onPin,
  running,
}: {
  item: Item;
  href: string;
  active: boolean;
  onRename: (title: string) => Promise<void>;
  onDelete: () => void;
  onPin?: () => void;
  running?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(item.title);
  const closeOnMobile = () => window.innerWidth < 768 && useApp.getState().setSidebarOpen(false);

  if (editing) {
    return (
      <input
        autoFocus
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        onBlur={async () => {
          setEditing(false);
          if (title.trim() && title !== item.title) await onRename(title.trim());
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            setTitle(item.title);
            setEditing(false);
          }
        }}
        className="w-full rounded-xl bg-gray-100 px-3 py-2 text-sm outline-none dark:bg-gray-850"
      />
    );
  }

  return (
    <div
      className={cn(
        "group relative flex items-center rounded-xl transition-colors",
        active ? "bg-gray-100 dark:bg-gray-850" : "hover:bg-gray-100 dark:hover:bg-gray-900",
      )}
    >
      <Link to={href} onClick={closeOnMobile} className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2 text-sm" onDoubleClick={() => setEditing(true)}>
        {running && <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-accent-500" />}
        {item.status === "error" && !running && <span className="size-1.5 shrink-0 rounded-full bg-red-500" />}
        <div className="min-w-0 flex-1">
          <div className="truncate">{item.title}</div>
          {item.subtitle && <div className="truncate text-[11px] text-gray-500">{item.subtitle}</div>}
        </div>
      </Link>
      <div className={cn("absolute right-1 hidden group-hover:block", active && "block")}>
        <Menu
          align="right"
          trigger={(_, toggle) => (
            <button
              onClick={toggle}
              className="rounded-lg p-1 text-gray-500 hover:bg-gray-200 hover:text-gray-900 dark:hover:bg-gray-800 dark:hover:text-gray-100"
            >
              <MoreHorizontal className="size-4" />
            </button>
          )}
        >
          {(close) => (
            <>
              {onPin && (
                <MenuItem
                  icon={item.pinned ? <PinOff className="size-4" /> : <Pin className="size-4" />}
                  onClick={() => {
                    close();
                    onPin();
                  }}
                >
                  {item.pinned ? "Unpin" : "Pin"}
                </MenuItem>
              )}
              <MenuItem
                icon={<Pencil className="size-4" />}
                onClick={() => {
                  close();
                  setEditing(true);
                }}
              >
                Rename
              </MenuItem>
              <MenuItem
                danger
                icon={<Trash2 className="size-4" />}
                onClick={() => {
                  close();
                  onDelete();
                }}
              >
                Delete
              </MenuItem>
            </>
          )}
        </Menu>
      </div>
    </div>
  );
}

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, config, signout } = useAuth();
  const { sidebarOpen, setSidebarOpen, chats, loadChats, upsertChat, removeChat, sessions, loadSessions, upsertSession, removeSession, openSettings } =
    useApp();
  const [search, setSearch] = useState("");
  const [confirm, setConfirm] = useState<{ kind: "chat" | "task"; id: string; title: string } | null>(null);
  const [deleteFiles, setDeleteFiles] = useState(false);

  const mode: "chat" | "cowork" = location.pathname.startsWith("/cowork") ? "cowork" : "chat";
  const coworkEnabled = user?.role === "admin" || config?.features.cowork;
  const activeId = location.pathname.split("/")[2];

  useEffect(() => {
    loadChats().catch(() => {});
    if (coworkEnabled) loadSessions();
  }, [loadChats, loadSessions, coworkEnabled]);

  // Poll task status while any task is running
  const anyRunning = sessions.some((s) => s.status === "running");
  useEffect(() => {
    if (!anyRunning) return;
    const t = setInterval(loadSessions, 4000);
    return () => clearInterval(t);
  }, [anyRunning, loadSessions]);

  const items: Item[] = useMemo(() => {
    const q = search.toLowerCase();
    if (mode === "chat") return chats.filter((c) => c.title.toLowerCase().includes(q));
    return sessions
      .filter((s) => s.title.toLowerCase().includes(q))
      .map((s) => ({ ...s, subtitle: s.repo_name ? `${s.repo_name}${s.branch ? ` · ${s.branch}` : ""}` : null }));
  }, [mode, chats, sessions, search]);
  const groups = groupByDate(items);

  const newItem = () => {
    navigate(mode === "chat" ? "/" : "/cowork");
    if (window.innerWidth < 768) setSidebarOpen(false);
  };

  return (
    <>
      {sidebarOpen && <div className="fixed inset-0 z-30 bg-black/40 md:hidden" onClick={() => setSidebarOpen(false)} />}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-[264px] shrink-0 flex-col bg-gray-50 transition-[margin,transform] duration-200 md:relative md:z-auto dark:bg-gray-950",
          sidebarOpen ? "translate-x-0" : "-translate-x-full md:-ml-[264px] md:translate-x-0",
        )}
      >
        <div className="flex items-center justify-between px-3 pt-3 pb-2">
          <Link to="/" className="flex items-center gap-2 px-1.5 font-semibold">
            <Logo className="size-6" />
            <span className="truncate">{config?.name ?? "Open Cowork"}</span>
          </Link>
          <IconButton label="Close sidebar" onClick={() => setSidebarOpen(false)}>
            <PanelLeftClose className="size-[18px]" />
          </IconButton>
        </div>

        {coworkEnabled && (
          <div className="mx-3 mb-2 grid grid-cols-2 gap-1 rounded-xl bg-gray-200/60 p-1 text-sm dark:bg-gray-900">
            {(["chat", "cowork"] as const).map((m) => (
              <button
                key={m}
                onClick={() => navigate(m === "chat" ? "/" : "/cowork")}
                className={cn(
                  "flex items-center justify-center gap-1.5 rounded-lg py-1.5 font-medium transition-colors",
                  mode === m
                    ? "bg-white text-gray-900 shadow-sm dark:bg-gray-800 dark:text-white"
                    : "text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100",
                )}
              >
                {m === "chat" ? <MessageSquare className="size-4" /> : <Bot className="size-4" />}
                {m === "chat" ? "Chat" : "Cowork"}
              </button>
            ))}
          </div>
        )}

        <div className="px-3">
          <button
            onClick={newItem}
            className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium transition-colors hover:bg-gray-100 dark:hover:bg-gray-900"
          >
            <SquarePen className="size-4" />
            {mode === "chat" ? "New chat" : "New task"}
          </button>
          {mode === "cowork" && (
            <Link
              to="/cowork/repos"
              onClick={() => window.innerWidth < 768 && setSidebarOpen(false)}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium transition-colors hover:bg-gray-100 dark:hover:bg-gray-900",
                location.pathname === "/cowork/repos" && "bg-gray-100 dark:bg-gray-850",
              )}
            >
              <FolderGit2 className="size-4" />
              Repositories
            </Link>
          )}
          <div className="mt-1 flex items-center gap-2 rounded-xl px-3 py-1.5 text-sm text-gray-500 focus-within:bg-gray-100 dark:focus-within:bg-gray-900">
            <Search className="size-4 shrink-0" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={mode === "chat" ? "Search chats" : "Search tasks"}
              className="w-full bg-transparent py-0.5 text-gray-900 outline-none placeholder:text-gray-500 dark:text-gray-100"
            />
          </div>
        </div>

        <nav className="mt-2 flex-1 overflow-y-auto px-3 pb-3">
          {groups.length === 0 && (
            <div className="px-3 py-8 text-center text-xs text-gray-500">
              {search ? "Nothing found" : mode === "chat" ? "No chats yet" : "No tasks yet"}
            </div>
          )}
          {groups.map((g) => (
            <div key={g.label} className="mb-3">
              <div className="px-3 pt-2 pb-1 text-xs font-medium text-gray-500">{g.label}</div>
              <div className="space-y-0.5">
                {g.items.map((it) =>
                  mode === "chat" ? (
                    <ItemRow
                      key={it.id}
                      item={it}
                      href={`/c/${it.id}`}
                      active={location.pathname === `/c/${it.id}`}
                      onRename={async (title) => {
                        await api.updateChat(it.id, { title });
                        upsertChat({ id: it.id, title });
                      }}
                      onPin={async () => {
                        await api.updateChat(it.id, { pinned: !it.pinned });
                        upsertChat({ id: it.id, pinned: !it.pinned });
                      }}
                      onDelete={() => setConfirm({ kind: "chat", id: it.id, title: it.title })}
                    />
                  ) : (
                    <ItemRow
                      key={it.id}
                      item={it}
                      href={`/cowork/${it.id}`}
                      active={mode === "cowork" && activeId === it.id}
                      running={it.status === "running"}
                      onRename={async (title) => {
                        await api.updateCoworkSession(it.id, { title });
                        upsertSession({ id: it.id, title });
                      }}
                      onDelete={() => setConfirm({ kind: "task", id: it.id, title: it.title })}
                    />
                  ),
                )}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t border-gray-200/70 p-2 dark:border-gray-900">
          <Menu
            side="top"
            className="w-[240px]"
            trigger={(_, toggle) => (
              <button
                onClick={toggle}
                className="flex w-full items-center gap-2.5 rounded-xl px-2 py-2 text-left transition-colors hover:bg-gray-100 dark:hover:bg-gray-900"
              >
                <Avatar name={user?.name ?? "?"} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{user?.name}</div>
                  <div className="truncate text-xs text-gray-500">{user?.email}</div>
                </div>
              </button>
            )}
          >
            {(close) => (
              <>
                <MenuItem
                  icon={<Settings className="size-4" />}
                  onClick={() => {
                    close();
                    openSettings();
                  }}
                >
                  Settings
                </MenuItem>
                {user?.role === "admin" && (
                  <MenuItem
                    icon={<Shield className="size-4" />}
                    onClick={() => {
                      close();
                      navigate("/admin");
                    }}
                  >
                    Admin panel
                  </MenuItem>
                )}
                <div className="my-1 border-t border-gray-100 dark:border-gray-800" />
                <MenuItem icon={<LogOut className="size-4" />} onClick={signout}>
                  Sign out
                </MenuItem>
              </>
            )}
          </Menu>
        </div>
      </aside>

      <ConfirmDialog
        open={!!confirm}
        title={confirm?.kind === "chat" ? "Delete chat?" : "Delete task?"}
        message={
          <>
            This will delete <strong>{confirm?.title}</strong>.
          </>
        }
        confirmLabel="Delete"
        danger
        onClose={() => {
          setConfirm(null);
          setDeleteFiles(false);
        }}
        onConfirm={async () => {
          if (!confirm) return;
          try {
            if (confirm.kind === "chat") {
              await api.deleteChat(confirm.id);
              removeChat(confirm.id);
              if (location.pathname === `/c/${confirm.id}`) navigate("/");
            } else {
              await api.deleteCoworkSession(confirm.id, deleteFiles);
              removeSession(confirm.id);
              if (activeId === confirm.id) navigate("/cowork");
            }
          } catch (e: any) {
            toast.error(e.message);
          }
        }}
      >
        {confirm?.kind === "task" && sessions.find((s) => s.id === confirm.id)?.workspace_type === "scratch" && (
          <label className="mt-3 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={deleteFiles} onChange={(e) => setDeleteFiles(e.target.checked)} />
            Also delete the task's workspace folder
          </label>
        )}
      </ConfirmDialog>
    </>
  );
}
