import { type FC } from "react";
import { ArrowRightIcon, Columns2Icon, Rows2Icon, XIcon } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/assistant-ui/project-status-badge";
import type { Project } from "@/lib/api";

function _formatDate(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export const ProjectDocument: FC<{
  project: Project;
  vertical: boolean;
  onToggleLayout: () => void;
  onClose: () => void;
}> = ({ project, vertical, onToggleLayout, onClose }) => {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-border flex items-center gap-2 border-b px-4 py-2">
        <h2 className="min-w-0 flex-1 truncate text-sm font-semibold">
          {project.name}
        </h2>
        <StatusBadge status={project.status} />
        {project.created_at && (
          <span className="text-muted-foreground hidden text-xs sm:inline">
            Created {_formatDate(project.created_at)}
          </span>
        )}
        <Button
          variant="ghost"
          size="icon"
          aria-label={
            vertical ? "Stack document and chat" : "Place document and chat side by side"
          }
          title={vertical ? "Stack vertically" : "Side by side"}
          onClick={onToggleLayout}
          className="size-7 shrink-0"
        >
          {vertical ? (
            <Rows2Icon className="size-4" />
          ) : (
            <Columns2Icon className="size-4" />
          )}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Close project"
          onClick={onClose}
          className="size-7 shrink-0"
        >
          <XIcon className="size-4" />
        </Button>
      </div>
      <div className="bg-muted/40 border-border flex items-start gap-2 border-b px-4 py-2">
        <ArrowRightIcon className="text-primary mt-0.5 size-4 shrink-0" />
        <div className="min-w-0">
          <div className="text-muted-foreground text-[10px] font-semibold tracking-wide uppercase">
            Next step
          </div>
          <div className="text-sm font-medium">
            {project.next_step?.trim() || (
              <span className="text-muted-foreground italic">Not set</span>
            )}
          </div>
        </div>
      </div>
      <div className="aui-project-document aui-md min-h-0 flex-1 overflow-y-auto px-4 py-3 text-sm break-words">
        {project.document.trim() ? (
          <Markdown remarkPlugins={[remarkGfm]}>{project.document}</Markdown>
        ) : (
          <span className="text-muted-foreground italic">No document yet.</span>
        )}
      </div>
    </div>
  );
};
