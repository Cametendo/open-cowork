import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowUp, ImagePlus, Square, X } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

export interface MessageInputProps {
  onSend: (text: string, images: string[]) => void;
  onStop?: () => void;
  busy?: boolean;
  disabled?: boolean;
  placeholder?: string;
  allowImages?: boolean;
  autoFocus?: boolean;
  /** Extra controls rendered in the toolbar (left side) */
  toolbar?: ReactNode;
  /** When busy, still allow sending (e.g. steering a running agent) */
  sendWhileBusy?: boolean;
  className?: string;
  large?: boolean;
}

function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",", 2)[1] ?? "");
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

export function MessageInput({
  onSend,
  onStop,
  busy,
  disabled,
  placeholder = "Send a message",
  allowImages,
  autoFocus,
  toolbar,
  sendWhileBusy,
  className,
  large,
}: MessageInputProps) {
  const [text, setText] = useState("");
  const [images, setImages] = useState<string[]>([]);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 320)}px`;
  }, [text]);

  useEffect(() => {
    if (autoFocus && window.innerWidth >= 768) ref.current?.focus();
  }, [autoFocus]);

  const addFiles = async (files: FileList | File[]) => {
    const imgs = Array.from(files).filter((f) => f.type.startsWith("image/"));
    if (!imgs.length) return;
    if (imgs.some((f) => f.size > 10 * 1024 * 1024)) {
      toast.error("Images must be smaller than 10 MB");
      return;
    }
    const b64 = await Promise.all(imgs.map(readAsBase64));
    setImages((prev) => [...prev, ...b64].slice(0, 6));
  };

  const canSend = !disabled && (text.trim().length > 0 || images.length > 0) && (!busy || sendWhileBusy);

  const submit = () => {
    if (!canSend) return;
    onSend(text.trim(), images);
    setText("");
    setImages([]);
  };

  return (
    <div
      className={cn(
        "rounded-3xl border border-gray-200 bg-white px-3 pt-2.5 pb-2 shadow-sm transition-colors focus-within:border-gray-300 dark:border-gray-800 dark:bg-gray-850 dark:focus-within:border-gray-700",
        className,
      )}
      onDragOver={(e) => allowImages && e.preventDefault()}
      onDrop={(e) => {
        if (!allowImages) return;
        e.preventDefault();
        addFiles(e.dataTransfer.files);
      }}
    >
      {images.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2 px-1">
          {images.map((img, i) => (
            <div key={i} className="group relative">
              <img src={`data:image/*;base64,${img}`} alt="" className="size-14 rounded-xl object-cover" />
              <button
                onClick={() => setImages(images.filter((_, j) => j !== i))}
                className="absolute -top-1.5 -right-1.5 hidden rounded-full bg-gray-900 p-0.5 text-white group-hover:block"
              >
                <X className="size-3" />
              </button>
            </div>
          ))}
        </div>
      )}
      <textarea
        ref={ref}
        rows={1}
        value={text}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => setText(e.target.value)}
        onPaste={(e) => {
          if (allowImages && e.clipboardData.files.length) {
            e.preventDefault();
            addFiles(e.clipboardData.files);
          }
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        className={cn(
          "w-full resize-none bg-transparent px-1.5 outline-none placeholder:text-gray-400 dark:placeholder:text-gray-500",
          large ? "min-h-16 text-base" : "min-h-7 text-[15px]",
        )}
      />
      <div className="mt-1 flex items-center gap-1">
        {allowImages && (
          <>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              multiple
              hidden
              onChange={(e) => {
                if (e.target.files) addFiles(e.target.files);
                e.target.value = "";
              }}
            />
            <button
              type="button"
              title="Attach images"
              onClick={() => fileRef.current?.click()}
              className="rounded-full p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:hover:bg-gray-800 dark:hover:text-gray-100"
            >
              <ImagePlus className="size-[18px]" />
            </button>
          </>
        )}
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1">{toolbar}</div>
        {busy && onStop && !(sendWhileBusy && text.trim()) ? (
          <button
            onClick={onStop}
            title="Stop"
            className="flex size-8 items-center justify-center rounded-full bg-gray-900 text-white hover:bg-gray-700 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
          >
            <Square className="size-3.5 fill-current" />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!canSend}
            title="Send"
            className="flex size-8 items-center justify-center rounded-full bg-gray-900 text-white transition hover:bg-gray-700 disabled:bg-gray-200 disabled:text-gray-400 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200 dark:disabled:bg-gray-800 dark:disabled:text-gray-600"
          >
            <ArrowUp className="size-4" strokeWidth={2.5} />
          </button>
        )}
      </div>
    </div>
  );
}
