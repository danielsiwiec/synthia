import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AuiIf,
  ThreadListItemPrimitive,
  ThreadListPrimitive,
  useThreadListItem,
  useThreadListItemRuntime,
} from "@assistant-ui/react";
import { PencilIcon, PlusIcon, TrashIcon } from "lucide-react";
import { useEffect, useRef, useState, type FC } from "react";

export const ThreadList: FC<{ onNavigate?: () => void }> = ({ onNavigate }) => {
  return (
    <ThreadListPrimitive.Root className="aui-root aui-thread-list-root flex flex-col gap-1">
      <ThreadListNew onNavigate={onNavigate} />
      <AuiIf condition={(s) => s.threads.isLoading}>
        <ThreadListSkeleton />
      </AuiIf>
      <AuiIf condition={(s) => !s.threads.isLoading}>
        <ThreadListPrimitive.Items>
          {() => <ThreadListItem onNavigate={onNavigate} />}
        </ThreadListPrimitive.Items>
      </AuiIf>
    </ThreadListPrimitive.Root>
  );
};

const ThreadListNew: FC<{ onNavigate?: () => void }> = ({ onNavigate }) => {
  return (
    <ThreadListPrimitive.New asChild>
      <Button
        variant="outline"
        onClick={() => onNavigate?.()}
        className="aui-thread-list-new hover:bg-muted data-active:bg-muted h-9 justify-start gap-2 rounded-lg px-3 text-sm"
      >
        <PlusIcon className="size-4" />
        New Thread
      </Button>
    </ThreadListPrimitive.New>
  );
};

const ThreadListSkeleton: FC = () => {
  return (
    <div className="flex flex-col gap-1">
      {Array.from({ length: 5 }, (_, i) => (
        <div
          key={i}
          role="status"
          aria-label="Loading threads"
          className="aui-thread-list-skeleton-wrapper flex h-9 items-center px-3"
        >
          <Skeleton className="aui-thread-list-skeleton h-4 w-full" />
        </div>
      ))}
    </div>
  );
};

const ThreadListItemRename: FC<{ onStart: () => void }> = ({ onStart }) => {
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label="Rename thread"
      onClick={(e) => {
        e.stopPropagation();
        onStart();
      }}
      className="aui-thread-list-item-rename hover:text-foreground size-7 p-0 opacity-0 transition-opacity group-hover:opacity-100 group-data-active:opacity-100"
    >
      <PencilIcon className="size-4" />
    </Button>
  );
};

const ThreadListItemEditor: FC<{ onDone: () => void }> = ({ onDone }) => {
  const runtime = useThreadListItemRuntime();
  const title = useThreadListItem((s) => s.title);
  const [value, setValue] = useState(title ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const commit = () => {
    const next = value.trim();
    if (next && next !== title) void runtime.rename(next);
    onDone();
  };

  return (
    <input
      ref={inputRef}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onClick={(e) => e.stopPropagation()}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          commit();
        } else if (e.key === "Escape") {
          e.preventDefault();
          onDone();
        }
      }}
      className="aui-thread-list-item-input bg-background focus-visible:ring-ring min-w-0 flex-1 rounded-sm px-1 text-sm focus-visible:ring-1 focus-visible:outline-none"
    />
  );
};

const ThreadListItem: FC<{ onNavigate?: () => void }> = ({ onNavigate }) => {
  const [editing, setEditing] = useState(false);
  const isMain = useThreadListItem((s) => s.isMain);
  return (
    <ThreadListItemPrimitive.Root className="aui-thread-list-item group hover:bg-muted focus-visible:bg-muted data-active:bg-muted flex h-9 items-center gap-2 rounded-lg transition-colors focus-visible:outline-none">
      {editing ? (
        <div className="flex h-full min-w-0 flex-1 items-center px-3">
          <ThreadListItemEditor onDone={() => setEditing(false)} />
        </div>
      ) : (
        <>
          <ThreadListItemPrimitive.Trigger
            onClick={() => {
              if (isMain) onNavigate?.();
            }}
            className="aui-thread-list-item-trigger flex h-full min-w-0 flex-1 items-center px-3 text-start text-sm"
          >
            <span className="aui-thread-list-item-title min-w-0 flex-1 truncate">
              <ThreadListItemPrimitive.Title fallback="New Chat" />
            </span>
          </ThreadListItemPrimitive.Trigger>
          <ThreadListItemRename onStart={() => setEditing(true)} />
          <ThreadListItemPrimitive.Delete asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Delete thread"
              className="aui-thread-list-item-delete hover:text-destructive me-2 size-7 p-0 opacity-0 transition-opacity group-hover:opacity-100 group-data-active:opacity-100"
            >
              <TrashIcon className="size-4" />
            </Button>
          </ThreadListItemPrimitive.Delete>
        </>
      )}
    </ThreadListItemPrimitive.Root>
  );
};
