import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { ArrowDown, Code2, FileText, Lightbulb, PanelLeft, Settings2, SquarePen } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { ChatParams } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useApp } from "@/store/app";
import { useAuth } from "@/store/auth";
import { useChats } from "@/store/chat";
import { ChatControls } from "@/components/chat/ChatControls";
import { Messages } from "@/components/chat/Messages";
import { MessageInput } from "@/components/MessageInput";
import { ModelSelector } from "@/components/ModelSelector";
import { IconButton, Logo, Spinner } from "@/components/ui";

const SUGGESTIONS = [
  { icon: Lightbulb, title: "Explain a concept", prompt: "Explain how vector databases work, with a simple analogy." },
  { icon: Code2, title: "Write some code", prompt: "Write a Python script that renames photos by the date they were taken." },
  { icon: FileText, title: "Draft a message", prompt: "Draft a friendly email asking my team for feedback on a project proposal." },
];

function useDefaultModel() {
  const user = useAuth((s) => s.user);
  const models = useApp((s) => s.models);
  return useCallback(() => {
    const preferred = user?.settings?.default_model;
    if (preferred && models.some((m) => m.id === preferred)) return preferred;
    try {
      const last = localStorage.getItem("last_model");
      if (last && models.some((m) => m.id === last)) return last;
    } catch {
      /* ignore */
    }
    return models[0]?.id ?? null;
  }, [user, models]);
}

export function TopBar({ children, right }: { children?: React.ReactNode; right?: React.ReactNode }) {
  const { sidebarOpen, setSidebarOpen } = useApp();
  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-1 bg-white/80 px-2 backdrop-blur dark:bg-gray-900/80">
      {!sidebarOpen && (
        <IconButton label="Open sidebar" onClick={() => setSidebarOpen(true)}>
          <PanelLeft className="size-[18px]" />
        </IconButton>
      )}
      <div className="flex min-w-0 flex-1 items-center">{children}</div>
      <div className="flex items-center gap-1">{right}</div>
    </header>
  );
}

export function ChatPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const user = useAuth((s) => s.user);
  const { modelsLoaded, upsertChat } = useApp();
  const chat = useChats((s) => (id ? s.chats[id] : undefined));
  const streaming = useChats((s) => (id ? !!s.streaming[id] : false));
  const { load, send, stop, patch } = useChats();
  const defaultModel = useDefaultModel();

  const [model, setModel] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [controlsOpen, setControlsOpen] = useState(false);
  const [draftParams, setDraftParams] = useState<ChatParams>({});
  const scrollRef = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);

  // Load the chat when navigating to it
  useEffect(() => {
    if (!id) {
      setDraftParams({});
      return;
    }
    if (useChats.getState().chats[id]) return;
    setLoading(true);
    load(id)
      .catch((e) => {
        toast.error(e.message);
        navigate("/");
      })
      .finally(() => setLoading(false));
  }, [id, load, navigate]);

  // Pick a model: the chat's, else the default
  useEffect(() => {
    if (chat?.model) setModel(chat.model);
    else if (modelsLoaded && !model) setModel(defaultModel());
  }, [chat?.model, modelsLoaded, defaultModel, model]);

  const chooseModel = (m: string) => {
    setModel(m);
    try {
      localStorage.setItem("last_model", m);
    } catch {
      /* ignore */
    }
    if (id) api.updateChat(id, { model: m }).catch(() => {});
  };

  // Auto-scroll while streaming if the user is at the bottom
  const messages = chat?.messages ?? [];
  const lastLen = messages[messages.length - 1]?.content.length ?? 0;
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && atBottom) el.scrollTop = el.scrollHeight;
  }, [messages.length, lastLen, atBottom]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  };

  const submit = async (text: string, images: string[]) => {
    if (!model) {
      toast.error("Select a model first");
      return;
    }
    let chatId = id;
    if (!chatId) {
      try {
        const created = await api.createChat({ model, params: draftParams });
        useChats.getState().set(created);
        upsertChat(created);
        chatId = created.id;
        navigate(`/c/${created.id}`);
      } catch (e: any) {
        toast.error(e.message);
        return;
      }
    }
    setAtBottom(true);
    send(chatId, { model, content: text, images: images.length ? images : undefined });
  };

  const params = chat?.params ?? draftParams;
  const updateParams = (p: ChatParams) => {
    if (id) {
      patch(id, { params: p });
      api.updateChat(id, { params: p }).catch((e) => toast.error(e.message));
    } else setDraftParams(p);
  };

  const empty = !id || (!loading && messages.length === 0);

  return (
    <div className="flex h-full min-w-0 flex-1">
      <div className="flex h-full min-w-0 flex-1 flex-col">
        <TopBar
          right={
            <>
              <IconButton label="Chat controls" onClick={() => setControlsOpen((v) => !v)} className={cn(controlsOpen && "bg-gray-100 dark:bg-gray-850")}>
                <Settings2 className="size-[18px]" />
              </IconButton>
              <IconButton label="New chat" onClick={() => navigate("/")} className="md:hidden">
                <SquarePen className="size-[18px]" />
              </IconButton>
            </>
          }
        >
          <ModelSelector value={model} onChange={chooseModel} />
        </TopBar>

        {loading ? (
          <div className="flex flex-1 items-center justify-center">
            <Spinner className="size-6 text-gray-400" />
          </div>
        ) : empty ? (
          <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-4 pb-16">
            <div className="w-full max-w-3xl">
              <div className="mb-8 flex items-center gap-3">
                <Logo className="size-10" />
                <div>
                  <div className="text-3xl font-medium">Hello, {user?.name?.split(" ")[0]}</div>
                  <div className="text-gray-500">How can I help you today?</div>
                </div>
              </div>
              <MessageInput autoFocus allowImages large onSend={submit} disabled={!model} placeholder="How can I help you today?" />
              <div className="mt-5 grid gap-2 sm:grid-cols-3">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s.title}
                    onClick={() => submit(s.prompt, [])}
                    className="rounded-2xl border border-gray-100 p-3 text-left transition-colors hover:bg-gray-50 dark:border-gray-850 dark:hover:bg-gray-850"
                  >
                    <s.icon className="mb-2 size-4 text-gray-500" />
                    <div className="text-sm font-medium">{s.title}</div>
                    <div className="mt-0.5 line-clamp-2 text-xs text-gray-500">{s.prompt}</div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <>
            <div ref={scrollRef} onScroll={onScroll} className="relative flex-1 overflow-y-auto">
              <Messages
                messages={messages}
                streaming={streaming}
                onRegenerate={() => model && id && send(id, { model, regenerate: true })}
                onEdit={(mid, content) => model && id && send(id, { model, content, editMessageId: mid })}
              />
            </div>
            <div className="relative mx-auto w-full max-w-3xl px-4 pb-4">
              {!atBottom && (
                <button
                  onClick={() => {
                    setAtBottom(true);
                    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
                  }}
                  className="absolute -top-12 left-1/2 -translate-x-1/2 rounded-full border border-gray-200 bg-white p-2 shadow-md dark:border-gray-800 dark:bg-gray-850"
                >
                  <ArrowDown className="size-4" />
                </button>
              )}
              <MessageInput
                autoFocus
                allowImages
                busy={streaming}
                onStop={() => id && stop(id)}
                onSend={submit}
                disabled={!model}
              />
              <div className="mt-2 text-center text-xs text-gray-400">
                Models can make mistakes. Check important information.
              </div>
            </div>
          </>
        )}
      </div>
      {controlsOpen && <ChatControls params={params} onChange={updateParams} onClose={() => setControlsOpen(false)} />}
    </div>
  );
}
