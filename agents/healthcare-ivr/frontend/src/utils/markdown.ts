export interface Section {
  id: string
  title: string
}

/** URL fragment for a heading, e.g. "Location and contact" becomes `location-and-contact`. */
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

/** The document's second-level headings, in order, for an "On this page" outline. */
export function sectionsOf(markdown: string): Section[] {
  return [...markdown.matchAll(/^## (.+)$/gm)].map(([, title]) => ({
    id: slugify(title.trim()),
    title: title.trim(),
  }))
}
