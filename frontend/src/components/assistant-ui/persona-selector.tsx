import { useState, type FC } from "react";
import { Popover as PopoverPrimitive } from "radix-ui";
import { TooltipIconButton } from "@/components/assistant-ui/tooltip-icon-button";
import { PERSONAS, personaById } from "@/lib/personas";
import { usePersona } from "@/runtime/personaContext";
import { cn } from "@/lib/utils";
import { DramaIcon } from "lucide-react";

export const PersonaSelector: FC = () => {
  const { persona, setPersona } = usePersona();
  const [open, setOpen] = useState(false);
  const active = personaById(persona);

  const select = (id: string | null) => {
    setPersona(id);
    setOpen(false);
  };

  return (
    <PopoverPrimitive.Root open={open} onOpenChange={setOpen}>
      <PopoverPrimitive.Trigger asChild>
        <TooltipIconButton
          tooltip={active ? `Persona: ${active.label}` : "Choose a persona"}
          side="bottom"
          type="button"
          variant="ghost"
          size="icon"
          className={cn(
            "aui-composer-persona hover:bg-muted-foreground/15 dark:hover:bg-muted-foreground/30 size-8 rounded-full p-1 text-base font-semibold",
            active && "bg-muted-foreground/15 dark:bg-muted-foreground/30",
          )}
          aria-label="Choose a persona"
        >
          {active ? (
            <span aria-hidden>{active.emoji}</span>
          ) : (
            <DramaIcon className="size-5 stroke-[1.5px]" />
          )}
        </TooltipIconButton>
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          side="top"
          align="start"
          sideOffset={8}
          className="bg-popover text-popover-foreground border-border z-50 w-64 origin-(--radix-popover-content-transform-origin) animate-in rounded-xl border p-1 shadow-md fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95"
        >
          <button
            type="button"
            onClick={() => select(null)}
            className={cn(
              "hover:bg-muted flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm",
              !persona && "bg-muted",
            )}
          >
            <span className="text-base" aria-hidden>
              ✨
            </span>
            <span className="font-medium">Default</span>
          </button>
          {PERSONAS.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => select(p.id)}
              className={cn(
                "hover:bg-muted flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm",
                persona === p.id && "bg-muted",
              )}
            >
              <span className="text-base" aria-hidden>
                {p.emoji}
              </span>
              <span className="min-w-0">
                <span className="block font-medium">{p.label}</span>
                <span className="text-muted-foreground block text-xs">{p.description}</span>
              </span>
            </button>
          ))}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
};
