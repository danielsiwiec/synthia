import { useEffect, useRef, useState } from "react";
import { PanelLeftCloseIcon, PanelLeftOpenIcon } from "lucide-react";
import { SynthiaProvider } from "./runtime/SynthiaProvider";
import { Thread } from "@/components/assistant-ui/thread";
import { ThreadList } from "@/components/assistant-ui/thread-list";
import { Button } from "@/components/ui/button";

export default function App() {
  const [collapsed, setCollapsed] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (collapsed) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!sidebarRef.current?.contains(event.target as Node)) {
        setCollapsed(true);
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [collapsed]);

  return (
    <SynthiaProvider>
      <div
        className={`grid h-full grid-rows-[minmax(0,1fr)] overflow-hidden ${
          collapsed
            ? "grid-cols-[minmax(0,1fr)]"
            : "grid-cols-[250px_minmax(0,1fr)]"
        }`}
      >
        {!collapsed && (
          <aside
            ref={sidebarRef}
            className="border-border flex min-h-0 flex-col border-r"
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
              <ThreadList />
            </div>
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
