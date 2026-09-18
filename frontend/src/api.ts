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

const jsonPost = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  me: () => apiFetch<{ user: User }>("/api/auth/me"),
  login: (username: string, password: string) =>
    apiFetch<{ user: User }>("/api/auth/login", jsonPost({ username, password })),
  logout: () => apiFetch("/api/auth/logout", { method: "POST" }),

  uploads: () => apiFetch<{ uploads: any[] }>("/api/uploads"),
  uploadFile: (form: FormData) =>
    apiFetch<{ id: number; filename: string; rows: number; columns: number }>("/api/uploads", { method: "POST", body: form }),
  uploadPreview: (id: number) => apiFetch<any>(`/api/uploads/${id}/preview`),

  users: () => apiFetch<{ users: any[] }>("/api/users"),
  createUser: (payload: { username: string; display_name: string; password: string; is_admin: boolean }) =>
    apiFetch("/api/users", jsonPost(payload)),
  renameUser: (id: number, display_name: string) =>
    apiFetch(`/api/users/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ display_name }) }),
  deleteUser: (id: number) => apiFetch(`/api/users/${id}`, { method: "DELETE" }),

  projects: () => apiFetch<{ projects: any[] }>("/api/projects"),
  createProject: (payload: { name: string; upload_id: number; settings?: any }) =>
    apiFetch<{ id: number }>("/api/projects", jsonPost(payload)),
  project: (id: number) => apiFetch<any>(`/api/projects/${id}`),
  projectData: (id: number, limit = 200) => apiFetch<any>(`/api/projects/${id}/data?limit=${limit}`),
  projectValues: (id: number, column: string) =>
    apiFetch<{ values: any[] }>(`/api/projects/${id}/values?column=${encodeURIComponent(column)}`),
  previewStep: (id: number, params: any) =>
    apiFetch<{ rows_before: number; rows_after: number }>(`/api/projects/${id}/steps/preview`, jsonPost({ type: "filter", params })),
  addStep: (id: number, params: any) => apiFetch<any>(`/api/projects/${id}/steps`, jsonPost({ type: "filter", params })),
  deleteStep: (projectId: number, stepId: number) =>
    apiFetch(`/api/projects/${projectId}/steps/${stepId}`, { method: "DELETE" }),
  frequencies: (id: number, column: string) =>
    apiFetch<any>(`/api/projects/${id}/frequencies?column=${encodeURIComponent(column)}`),
  exportUrl: (id: number, column?: string) =>
    `/api/projects/${id}/export${column ? `?column=${encodeURIComponent(column)}` : ""}`,
};
