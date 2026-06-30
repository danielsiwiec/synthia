import { useState, type FC } from "react";
import {
  ArrowRightIcon,
  Columns2Icon,
  GripVerticalIcon,
  Rows2Icon,
  XIcon,
} from "lucide-react";
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { StatusBadge } from "@/components/assistant-ui/project-status-badge";
import {
  reorderProjectSections,
  type Project,
  type ProjectMedia,
  type ProjectSection,
} from "@/lib/api";

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

const SortableSection: FC<{ section: ProjectSection }> = ({ section }) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: section.id });
  return (
    <section
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`aui-project-section group border-border bg-background relative rounded-lg border p-3 ${
        isDragging ? "z-10 opacity-80 shadow-md" : ""
      }`}
    >
      <div className="mb-1 flex items-center gap-1.5">
        <button
          type="button"
          aria-label="Drag to reorder section"
          className="text-muted-foreground hover:text-foreground cursor-grab touch-none active:cursor-grabbing"
          {...attributes}
          {...listeners}
        >
          <GripVerticalIcon className="size-4" />
        </button>
        <h3 className="min-w-0 flex-1 truncate text-sm font-semibold">
          {section.title || "Untitled section"}
        </h3>
      </div>
      <div className="aui-md text-sm break-words">
        {section.body.trim() ? (
          <Markdown remarkPlugins={[remarkGfm]}>{section.body}</Markdown>
        ) : (
          <span className="text-muted-foreground italic">Empty section.</span>
        )}
      </div>
    </section>
  );
};

const MediaItem: FC<{ item: ProjectMedia }> = ({ item }) => {
  const isImage = Boolean(item.content_type.startsWith("image/") && item.url);
  return (
    <figure className="border-border bg-background overflow-hidden rounded-lg border">
      {isImage ? (
        <Dialog>
          <DialogTrigger asChild>
            <button
              type="button"
              aria-label={`Expand ${item.caption || item.name}`}
              className="block w-full cursor-zoom-in"
            >
              <img
                src={item.url ?? undefined}
                alt={item.caption || item.name}
                className="max-h-80 w-full object-contain transition-opacity hover:opacity-90"
              />
            </button>
          </DialogTrigger>
          <DialogContent className="max-w-[95vw] p-2 sm:max-w-4xl">
            <DialogTitle className="sr-only">{item.caption || item.name}</DialogTitle>
            <img
              src={item.url ?? undefined}
              alt={item.caption || item.name}
              className="mx-auto block max-h-[85vh] w-auto max-w-full object-contain"
            />
            {item.caption && (
              <div className="text-muted-foreground px-1 pt-1 text-center text-xs">
                {item.caption}
              </div>
            )}
          </DialogContent>
        </Dialog>
      ) : (
        <a
          href={item.url ?? undefined}
          target="_blank"
          rel="noreferrer"
          className="text-primary block truncate px-3 py-2 text-sm underline"
        >
          {item.name}
        </a>
      )}
      {item.caption && (
        <figcaption className="text-muted-foreground px-3 py-1.5 text-xs">
          {item.caption}
        </figcaption>
      )}
    </figure>
  );
};

export const ProjectDocument: FC<{
  project: Project;
  vertical: boolean;
  onToggleLayout: () => void;
  onClose: () => void;
}> = ({ project, vertical, onToggleLayout, onClose }) => {
  const [localOrder, setLocalOrder] = useState<string[]>(() =>
    project.sections.map((s) => s.id),
  );

  const serverIds = project.sections.map((s) => s.id);
  const known = new Set(serverIds);
  const order = [
    ...localOrder.filter((id) => known.has(id)),
    ...serverIds.filter((id) => !localOrder.includes(id)),
  ];

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
  );

  const sectionsById = new Map(project.sections.map((s) => [s.id, s]));
  const orderedSections = order
    .map((id) => sectionsById.get(id))
    .filter((s): s is ProjectSection => Boolean(s));

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = order.indexOf(String(active.id));
    const to = order.indexOf(String(over.id));
    if (from < 0 || to < 0) return;
    const next = arrayMove(order, from, to);
    setLocalOrder(next);
    void reorderProjectSections(project.id, next).catch(() => {});
  };

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
      <div className="aui-project-document min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {orderedSections.length > 0 && (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={onDragEnd}
          >
            <SortableContext
              items={order}
              strategy={verticalListSortingStrategy}
            >
              <div className="space-y-2">
                {orderedSections.map((section) => (
                  <SortableSection key={section.id} section={section} />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        )}

        <div className="aui-md text-sm break-words">
          {project.document.trim() ? (
            <Markdown remarkPlugins={[remarkGfm]}>{project.document}</Markdown>
          ) : (
            orderedSections.length === 0 && (
              <span className="text-muted-foreground italic">No document yet.</span>
            )
          )}
        </div>

        {project.media.length > 0 && (
          <div className="border-border space-y-2 border-t pt-3">
            <div className="text-muted-foreground text-[10px] font-semibold tracking-wide uppercase">
              Media
            </div>
            <div className="space-y-2">
              {project.media.map((item) => (
                <MediaItem key={item.id} item={item} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
