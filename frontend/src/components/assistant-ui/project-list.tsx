import { type FC } from "react";
import { FolderIcon } from "lucide-react";
import { StatusBadge } from "@/components/assistant-ui/project-status-badge";
import type { Project } from "@/lib/api";

export const ProjectList: FC<{
  projects: Project[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}> = ({ projects, selectedId, onSelect }) => {
  if (projects.length === 0) return null;

  return (
    <div className="aui-project-list mb-3 flex flex-col gap-0.5">
      <div className="text-muted-foreground flex items-center gap-1.5 px-2 py-1 text-xs font-semibold tracking-wide uppercase">
        <FolderIcon className="size-3.5" />
        Projects
      </div>
      {projects.map((project) => (
        <button
          key={project.id}
          type="button"
          onClick={() => onSelect(project.id)}
          aria-pressed={selectedId === project.id}
          className={`aui-project-list-item flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-start transition-colors ${
            selectedId === project.id ? "bg-muted" : "hover:bg-muted"
          }`}
        >
          <span className="min-w-0 flex-1 truncate text-sm font-medium">
            {project.name}
          </span>
          <StatusBadge status={project.status} />
        </button>
      ))}
    </div>
  );
};
