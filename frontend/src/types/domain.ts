/** Shared frontend domain contracts. Keep aligned with backend/campuscare/schemas.py. */
export type Category = "academic" | "hostel" | "library" | "cafeteria" | "transport" | "it_network" | "other"
export type Status = "pending" | "in_progress" | "resolved" | "rejected"
export type Role = "user" | "admin"
export type Page = "home" | "about" | "complaints" | "profile" | "contact" | "admin" | "users"

export type Complaint = {
  id: number
  owner_id?: number | null
  title: string
  description: string
  category: Category
  status: Status
  admin_response: string | null
  created_at: string
  updated_at: string
}

export type ComplaintForm = { title: string; description: string; category: Category }

export const categories: { value: Category; label: string }[] = [
  { value: "academic", label: "Academic" },
  { value: "hostel", label: "Hostel" },
  { value: "library", label: "Library" },
  { value: "cafeteria", label: "Cafeteria" },
  { value: "transport", label: "Transport" },
  { value: "it_network", label: "IT & Network" },
  { value: "other", label: "Other" },
]

export const statuses: { value: Status; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "in_progress", label: "In progress" },
  { value: "resolved", label: "Resolved" },
  { value: "rejected", label: "Rejected" },
]

export const PAGES: Page[] = ["home", "about", "complaints", "profile", "contact", "admin", "users"]
export const emptyForm: ComplaintForm = { title: "", description: "", category: "academic" }

export type ManagedUser = {
  id: number
  email: string
  full_name: string
  role: Role
  is_banned: boolean
  status: "active" | "suspended" | "banned"
  suspended_until: string | null
  suspension_reason: string | null
  ban_reason: string | null
  created_at: string
}
