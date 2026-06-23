export interface PersonaOption {
  id: string;
  label: string;
  emoji: string;
  description: string;
}

export const PERSONAS: PersonaOption[] = [
  { id: "white", label: "White Hat", emoji: "⚪", description: "Facts, data, neutral analysis" },
  { id: "red", label: "Red Hat", emoji: "🔴", description: "Emotions, gut feeling, intuition" },
  { id: "black", label: "Black Hat", emoji: "⚫", description: "Caution, risks, critical judgment" },
  { id: "yellow", label: "Yellow Hat", emoji: "🟡", description: "Optimism, benefits, value" },
  { id: "green", label: "Green Hat", emoji: "🟢", description: "Creativity, alternatives, ideas" },
  { id: "blue", label: "Blue Hat", emoji: "🔵", description: "Process, structure, big picture" },
];

export function personaById(id: string | null): PersonaOption | null {
  if (!id) return null;
  return PERSONAS.find((p) => p.id === id) ?? null;
}
