import { type FC } from "react";
import type { Project } from "@/lib/api";

export const StatusBadge: FC<{ status: Project["status"] }> = ({ status }) => {
  const isActive = status === "active";
  return (
    <span
      className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium uppercase ${
        isActive
          ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
          : "bg-muted text-muted-foreground"
      }`}
    >
      {status}
    </span>
  );
};
