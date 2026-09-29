import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { SectionView } from "@/components/views/section-view";
import { findNavItem } from "@/lib/navigation";

async function resolve(params: Promise<{ section: string }>) {
  const { section } = await params;
  const item = findNavItem(`/${section}`);
  return item?.phase ? item : null;
}

export async function generateMetadata(props: PageProps<"/[section]">): Promise<Metadata> {
  const item = await resolve(props.params);
  return { title: item?.label ?? "Not found" };
}

export default async function SectionPage(props: PageProps<"/[section]">) {
  const item = await resolve(props.params);
  if (!item) notFound();
  return <SectionView item={item} />;
}
