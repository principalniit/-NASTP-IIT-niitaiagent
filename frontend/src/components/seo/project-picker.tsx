"use client";

import { useState } from "react";

import { NativeSelect } from "@/components/ui/native-select";
import { useProjects } from "@/lib/queries";
import type { Project } from "@/lib/types";

const STORAGE_KEY = "niit-seo.selected-project";

function stored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/** Selected project shared across SEO pages, remembered per browser. */
export function useProjectChoice(orgId: string | null) {
  const projects = useProjects(orgId, { sort: "name", order: "asc" });
  const [chosen, setChosen] = useState<string | null>(stored);
  const list = projects.data?.items ?? [];
  const project: Project | null = list.find((p) => p.id === chosen) ?? list[0] ?? null;
  return {
    projects: list,
    project,
    isLoading: projects.isLoading,
    choose: (id: string) => {
      setChosen(id);
      try {
        window.localStorage.setItem(STORAGE_KEY, id);
      } catch {
        // Storage can be unavailable; the choice still applies to this page.
      }
    },
  };
}

export function ProjectPicker({
  projects,
  project,
  onChange,
}: {
  projects: Project[];
  project: Project | null;
  onChange: (id: string) => void;
}) {
  if (projects.length <= 1) return null;
  return (
    <div className="flex items-center gap-2">
      <label htmlFor="seo-project" className="text-sm font-medium">
        Project
      </label>
      <NativeSelect id="seo-project" className="w-64" value={project?.id ?? ""} onChange={(e) => onChange(e.target.value)}>
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name} ({p.domain})
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}
