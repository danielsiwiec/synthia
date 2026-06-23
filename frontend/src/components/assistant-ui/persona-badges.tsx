import type { FC } from "react";
import { personaById, type PersonaOption } from "@/lib/personas";
import { cn } from "@/lib/utils";

const Chip: FC<{ persona: PersonaOption; muted?: boolean; title: string }> = ({
  persona,
  muted,
  title,
}) => {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs",
        muted
          ? "border-border text-muted-foreground"
          : "border-transparent bg-muted text-foreground",
      )}
    >
      <span aria-hidden>{persona.emoji}</span>
      <span>{persona.label}</span>
    </span>
  );
};

export const PersonaBadges: FC<{ persona?: string | null; consulted?: string[] }> = ({
  persona,
  consulted,
}) => {
  const selected = personaById(persona ?? null);
  const consultedList = (consulted ?? [])
    .filter((id) => id !== persona)
    .map((id) => personaById(id))
    .filter((p): p is PersonaOption => p !== null);

  if (!selected && consultedList.length === 0) return null;

  return (
    <div className="mb-1.5 flex flex-wrap items-center gap-1 px-2">
      {selected && (
        <Chip persona={selected} title={`Answered in the ${selected.label} persona`} />
      )}
      {consultedList.map((p) => (
        <Chip key={p.id} persona={p} muted title={`Consulted the ${p.label}`} />
      ))}
    </div>
  );
};
