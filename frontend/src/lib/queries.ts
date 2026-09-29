"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  AuditLogEntry,
  Health,
  Member,
  Organisation,
  Page,
  Project,
  ProjectSettings,
} from "@/lib/types";

export const keys = {
  health: ["health"] as const,
  organisations: ["organisations"] as const,
  organisation: (id: string) => ["organisations", id] as const,
  members: (orgId: string) => ["organisations", orgId, "members"] as const,
  audit: (orgId: string, page: number) => ["organisations", orgId, "audit", page] as const,
  projects: (orgId: string) => ["organisations", orgId, "projects"] as const,
  project: (id: string) => ["projects", id] as const,
  projectSettings: (id: string) => ["projects", id, "settings"] as const,
};

export function useHealth() {
  return useQuery({ queryKey: keys.health, queryFn: () => api<Health>("/health") });
}

export function useOrganisations(enabled = true) {
  return useQuery({
    queryKey: keys.organisations,
    queryFn: () => api<Page<Organisation>>("/organisations", { query: { page_size: 100 } }),
    enabled,
  });
}

export function useOrganisation(id: string | null) {
  return useQuery({
    queryKey: keys.organisation(id ?? ""),
    queryFn: () => api<Organisation>(`/organisations/${id}`),
    enabled: !!id,
  });
}

export function useMembers(orgId: string | null, enabled = true) {
  return useQuery({
    queryKey: keys.members(orgId ?? ""),
    queryFn: () => api<Page<Member>>(`/organisations/${orgId}/members`, { query: { page_size: 100 } }),
    enabled: !!orgId && enabled,
  });
}

export function useAuditLogs(orgId: string | null, page: number, enabled = true) {
  return useQuery({
    queryKey: keys.audit(orgId ?? "", page),
    queryFn: () =>
      api<Page<AuditLogEntry>>(`/organisations/${orgId}/audit-logs`, {
        query: { page, page_size: 20 },
      }),
    enabled: !!orgId && enabled,
  });
}

export interface ProjectQuery {
  q?: string;
  sort?: "name" | "created_at" | "domain";
  order?: "asc" | "desc";
  page?: number;
}

export function useProjects(orgId: string | null, params: ProjectQuery = {}, enabled = true) {
  return useQuery({
    queryKey: [...keys.projects(orgId ?? ""), params],
    queryFn: () =>
      api<Page<Project>>(`/organisations/${orgId}/projects`, {
        query: { page_size: 25, ...params },
      }),
    enabled: !!orgId && enabled,
  });
}

export function useProject(id: string) {
  return useQuery({ queryKey: keys.project(id), queryFn: () => api<Project>(`/projects/${id}`) });
}

export function useProjectSettings(id: string) {
  return useQuery({
    queryKey: keys.projectSettings(id),
    queryFn: () => api<ProjectSettings>(`/projects/${id}/settings`),
  });
}
