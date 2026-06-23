import { useCallback, useEffect, useRef, useState } from "react";
import { PanelLeftCloseIcon, PanelLeftOpenIcon } from "lucide-react";
import { SynthiaProvider } from "./runtime/SynthiaProvider";
import { Thread } from "@/components/assistant-ui/thread";
import { ThreadList } from "@/components/assistant-ui/thread-list";
import { ProjectList } from "@/components/assistant-ui/project-list";
import { ProjectDocument } from "@/components/assistant-ui/project-document";
import { Button } from "@/components/ui/button";
import { listProjects, type Project } from "@/lib/api";

const _PROJECT_POLL_INTERVAL = 5000;

const _MIN_SIDEBAR_WIDTH = 180;
const _MAX_SIDEBAR_WIDTH = 600;
const _DEFAULT_SIDEBAR_WIDTH = 250;
const _SIDEBAR_WIDTH_KEY = "synthia.sidebarWidth";
const _SPLIT_VERTICAL_KEY = "synthia.splitVertical";

function _readStoredWidth() {
  const stored = Number(localStorage.getItem(_SIDEBAR_WIDTH_KEY));
  if (!Number.isFinite(stored) || stored <= 0) return _DEFAULT_SIDEBAR_WIDTH;
  return Math.min(_MAX_SIDEBAR_WIDTH, Math.max(_MIN_SIDEBAR_WIDTH, stored));
}

export default function App() {
  const [collapsed, setCollapsed] = useState(false);
  const [width, setWidth] = useState(_readStoredWidth);
  const [resizing, setResizing] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [splitVertical, setSplitVertical] = useState(
    () => localStorage.getItem(_SPLIT_VERTICAL_KEY) === "1",
  );
  const sidebarRef = useRef<HTMLElement>(null);

  const selectedProject =
    projects.find((p) => p.id === selectedProjectId) ?? null;

  const refreshProjects = useCallback(() => {
    void listProjects()
      .then(setProjects)
      .catch(() => {});
  }, []);

  useEffect(() => {
    refreshProjects();
    const timer = window.setInterval(refreshProjects, _PROJECT_POLL_INTERVAL);
    const onVisible = () => {
      if (!document.hidden) refreshProjects();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refreshProjects]);

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

  useEffect(() => {
    localStorage.setItem(_SPLIT_VERTICAL_KEY, splitVertical ? "1" : "0");
  }, [splitVertical]);

  return (
    <SynthiaProvider
      selectedProjectId={selectedProjectId}
      onThreadSelect={() => setSelectedProjectId(null)}
      onAgentResult={refreshProjects}
      onProjectSelected={(id) => {
        setSelectedProjectId(id);
        refreshProjects();
      }}
    >
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
              <ProjectList
                projects={projects}
                selectedId={selectedProjectId}
                onSelect={(id) =>
                  setSelectedProjectId((cur) => (cur === id ? null : id))
                }
              />
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
          {selectedProject ? (
            <div
              className={`grid h-full min-h-0 ${
                splitVertical ? "grid-cols-2" : "grid-rows-2"
              }`}
            >
              <div
                className={`border-border min-h-0 overflow-hidden ${
                  splitVertical ? "order-2 border-l-2" : "order-1 border-b-2"
                }`}
              >
                <ProjectDocument
                  project={selectedProject}
                  vertical={splitVertical}
                  onToggleLayout={() => setSplitVertical((v) => !v)}
                  onClose={() => setSelectedProjectId(null)}
                />
              </div>
              <div
                className={`min-h-0 overflow-hidden ${
                  splitVertical ? "order-1" : "order-2"
                }`}
              >
                <Thread />
              </div>
            </div>
          ) : (
            <Thread />
          )}
        </main>
      </div>
    </SynthiaProvider>
  );
}
