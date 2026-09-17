export type User = {
  id: number;
  username: string;
  display_name: string;
  is_admin: boolean;
};

async function apiFetch<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { credentials: "same-origin", ...options });
  if (!response.ok) {
    let message = `Ошибка ${response.status}`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return response.json();
}

export const api = {
  me: () => apiFetch<{ user: User }>("/api/auth/me"),
  login: (username: string, password: string) =>
    apiFetch<{ user: User }>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  logout: () => apiFetch("/api/auth/logout", { method: "POST" }),
  uploads: () => apiFetch<{ uploads: any[] }>("/api/uploads"),
  uploadFile: (form: FormData) => apiFetch<{ id: number; filename: string; rows: number; columns: number }>("/api/uploads", { method: "POST", body: form }),
  users: () => apiFetch<{ users: any[] }>("/api/users"),
  createUser: (payload: { username: string; display_name: string; password: string; is_admin: boolean }) =>
    apiFetch("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  renameUser: (id: number, display_name: string) =>
    apiFetch(`/api/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name }),
    }),
  deleteUser: (id: number) => apiFetch(`/api/users/${id}`, { method: "DELETE" }),
};
