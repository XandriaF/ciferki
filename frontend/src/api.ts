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

const jsonPatch = (body: unknown): RequestInit => ({
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

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
  renameUser: (id: number, display_name: string) => apiFetch(`/api/users/${id}`, jsonPatch({ display_name })),
  deleteUser: (id: number) => apiFetch(`/api/users/${id}`, { method: "DELETE" }),

  projects: () => apiFetch<{ projects: any[] }>("/api/projects"),
  createProject: (payload: { name: string; upload_id?: number; settings?: any }) =>
    apiFetch<{ id: number }>("/api/projects", jsonPost(payload)),
  renameProject: (id: number, name: string) => apiFetch(`/api/projects/${id}`, jsonPatch({ name })),
  deleteProject: (id: number) => apiFetch(`/api/projects/${id}`, { method: "DELETE" }),
  project: (id: number) => apiFetch<any>(`/api/projects/${id}`),
  projectData: (id: number, limit = 200) => apiFetch<any>(`/api/projects/${id}/data?limit=${limit}`),
  projectValues: (id: number, column: string) =>
    apiFetch<{ values: any[] }>(`/api/projects/${id}/values?column=${encodeURIComponent(column)}`),

  addProjectFile: (id: number, payload: { upload_id: number; role: string; key_column?: string; wave_label?: string }) =>
    apiFetch<{ id: number }>(`/api/projects/${id}/files`, jsonPost(payload)),
  updateProjectFile: (id: number, fileId: number, payload: any) =>
    apiFetch(`/api/projects/${id}/files/${fileId}`, jsonPatch(payload)),
  deleteProjectFile: (id: number, fileId: number) =>
    apiFetch(`/api/projects/${id}/files/${fileId}`, { method: "DELETE" }),

  matchPreview: (id: number, payload: any) => apiFetch<any>(`/api/projects/${id}/match/preview`, jsonPost(payload)),

  previewStep: (id: number, params: any) =>
    apiFetch<{ rows_before: number; rows_after: number }>(`/api/projects/${id}/steps/preview`, jsonPost({ type: "filter", params })),
  addStep: (id: number, type: string, params: any) => apiFetch<any>(`/api/projects/${id}/steps`, jsonPost({ type, params })),
  deleteStep: (projectId: number, stepId: number) =>
    apiFetch(`/api/projects/${projectId}/steps/${stepId}`, { method: "DELETE" }),

  runTask: (id: number, task: string, config: any, save = true) =>
    apiFetch<any>(`/api/projects/${id}/tasks/run`, jsonPost({ task, config, save })),
  frequencies: (id: number, column: string) =>
    apiFetch<any>(`/api/projects/${id}/frequencies?column=${encodeURIComponent(column)}`),
  exportProject: async (id: number, payload: any) => {
    const response = await fetch(`/api/projects/${id}/export`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`Ошибка экспорта ${response.status}`);
    return response.blob();
  },
};
