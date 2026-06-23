import { createContext, useContext } from "react";

export interface PersonaContextValue {
  persona: string | null;
  setPersona: (persona: string | null) => void;
}

export const PersonaContext = createContext<PersonaContextValue>({
  persona: null,
  setPersona: () => {},
});

export function usePersona(): PersonaContextValue {
  return useContext(PersonaContext);
}
