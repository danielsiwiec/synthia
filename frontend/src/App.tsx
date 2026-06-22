import { useEffect, useRef, useState } from "react";
import { PanelLeftCloseIcon, PanelLeftOpenIcon } from "lucide-react";
import { SynthiaProvider } from "./runtime/SynthiaProvider";
import { Thread } from "@/components/assistant-ui/thread";
import { ThreadList } from "@/components/assistant-ui/thread-list";
import { Button } from "@/components/ui/button";

const _MIN_SIDEBAR_WIDTH = 180;
const _MAX_SIDEBAR_WIDTH = 600;
const _DEFAULT_SIDEBAR_WIDTH = 250;
const _SIDEBAR_WIDTH_KEY = "synthia.sidebarWidth";

function _readStoredWidth() {
  const stored = Number(localStorage.getItem(_SIDEBAR_WIDTH_KEY));
  if (!Number.isFinite(stored) || stored <= 0) return _DEFAULT_SIDEBAR_WIDTH;
  return Math.min(_MAX_SIDEBAR_WIDTH, Math.max(_MIN_SIDEBAR_WIDTH, stored));
}

export default function App() {
  const [collapsed, setCollapsed] = useState(false);
  const [width, setWidth] = useState(_readStoredWidth);
  const [resizing, setResizing] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (collapsed || resizing) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!sidebarRef.current?.contains(event.target as Node)) {
        setCollapsed(true);
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [collapsed, resizing]);

  useEffect(() => {
    if (!resizing) return;
    const handlePointerMove = (event: PointerEvent) => {
      const left = sidebarRef.current?.getBoundingClientRect().left ?? 0;
      const next = Math.min(
        _MAX_SIDEBAR_WIDTH,
        Math.max(_MIN_SIDEBAR_WIDTH, event.clientX - left),
      );
      setWidth(next);
    };
    const handlePointerUp = () => setResizing(false);
    document.addEventListener("pointermove", handlePointerMove);
    document.addEventListener("pointerup", handlePointerUp);
    return () => {
      document.removeEventListener("pointermove", handlePointerMove);
      document.removeEventListener("pointerup", handlePointerUp);
    };
  }, [resizing]);

  useEffect(() => {
    localStorage.setItem(_SIDEBAR_WIDTH_KEY, String(width));
  }, [width]);

  return (
    <SynthiaProvider>
      <div
        className={`grid h-full grid-rows-[minmax(0,1fr)] overflow-hidden ${
          collapsed ? "grid-cols-[minmax(0,1fr)]" : ""
        } ${resizing ? "cursor-col-resize select-none" : ""}`}
        style={
          collapsed
            ? undefined
            : { gridTemplateColumns: `${width}px minmax(0,1fr)` }
        }
      >
        {!collapsed && (
          <aside
            ref={sidebarRef}
            className="border-border relative flex min-h-0 flex-col border-r"
          >
            <div className="flex items-center justify-end p-2">
              <Button
                variant="ghost"
                size="icon"
                aria-label="Collapse sidebar"
                onClick={() => setCollapsed(true)}
              >
                <PanelLeftCloseIcon className="size-4" />
              </Button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 pb-2">
              <ThreadList onNavigate={() => setCollapsed(true)} />
            </div>
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize sidebar"
              onPointerDown={(event) => {
                event.preventDefault();
                setResizing(true);
              }}
              onDoubleClick={() => setWidth(_DEFAULT_SIDEBAR_WIDTH)}
              className="hover:bg-border absolute top-0 -right-1 z-10 h-full w-2 cursor-col-resize touch-none"
            />
          </aside>
        )}

        <main className="relative min-h-0 overflow-hidden">
          {collapsed && (
            <Button
              variant="ghost"
              size="icon"
              aria-label="Expand sidebar"
              onClick={() => setCollapsed(false)}
              className="bg-background absolute top-2 left-2 z-10"
            >
              <PanelLeftOpenIcon className="size-4" />
            </Button>
          )}
          <Thread />
        </main>
      </div>
    </SynthiaProvider>
  );
}
