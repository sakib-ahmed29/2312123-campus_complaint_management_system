import { PAGES } from "../types/domain"
import type { Page } from "../types/domain"

export function pageFromHash(): Page {
  const value = window.location.hash.replace(/^#\/?/, "")
  return (PAGES as string[]).includes(value) ? (value as Page) : "home"
}
