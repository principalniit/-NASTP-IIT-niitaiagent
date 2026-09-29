// Simple line-based editors for list settings. One entry per line, fields separated by "|".

export const splitLines = (text: string) =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

export const splitList = (text: string | undefined) =>
  (text ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

const parts = (line: string) => line.split("|").map((p) => p.trim());

export function parsePageGroups(text: string) {
  return splitLines(text).map((line) => {
    const [name, patterns] = parts(line);
    return { name: name ?? "", patterns: splitList(patterns) };
  });
}

export function formatPageGroups(groups: { name: string; patterns: string[] }[]) {
  return groups.map((g) => `${g.name} | ${g.patterns.join(", ")}`).join("\n");
}

export function parseContentTypes(text: string) {
  return splitLines(text).map((line) => {
    const [key, label, patterns, sections] = parts(line);
    return {
      key: key ?? "",
      label: label ?? "",
      url_patterns: splitList(patterns),
      expected_sections: splitList(sections),
    };
  });
}

export function formatContentTypes(
  types: { key: string; label: string; url_patterns: string[]; expected_sections: string[] }[],
) {
  return types
    .map((t) => {
      const fields = [t.key, t.label, t.url_patterns.join(", "), t.expected_sections.join(", ")];
      while (fields.length > 2 && !fields[fields.length - 1]) fields.pop();
      return fields.join(" | ");
    })
    .join("\n");
}

export function parseSources(text: string) {
  return splitLines(text).map((line) => {
    const [label, url] = parts(line);
    return { label: label ?? "", url: url ?? "" };
  });
}

export function formatSources(sources: { label: string; url: string }[]) {
  return sources.map((s) => `${s.label} | ${s.url}`).join("\n");
}

export function parseTerminology(text: string) {
  return splitLines(text).map((line) => {
    const [preferred, avoid, note] = parts(line);
    return { preferred: preferred ?? "", avoid: splitList(avoid), note: note || null };
  });
}

export function formatTerminology(
  entries: { preferred: string; avoid: string[]; note: string | null }[],
) {
  return entries
    .map((e) => [e.preferred, e.avoid.join(", "), e.note ?? ""].join(" | ").replace(/( \| )+$/, ""))
    .join("\n");
}
