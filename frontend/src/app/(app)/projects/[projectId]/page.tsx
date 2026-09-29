import type { Metadata } from "next";

import { ProjectDetailView } from "@/components/views/project-detail-view";

export const metadata: Metadata = { title: "Project" };

export default async function ProjectPage(props: PageProps<"/projects/[projectId]">) {
  const { projectId } = await props.params;
  return <ProjectDetailView projectId={projectId} />;
}
