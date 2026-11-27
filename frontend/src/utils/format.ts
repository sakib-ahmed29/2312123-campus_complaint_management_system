import { categories, statuses } from "../types/domain"
import type { Category, Status } from "../types/domain"

export function labelForCategory(value: Category) {
  return categories.find((item) => item.value === value)?.label ?? value
}
export function labelForStatus(value: Status) {
  return statuses.find((item) => item.value === value)?.label ?? value
}
export function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
}
