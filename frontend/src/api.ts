import type {
  Analysis,
  Attachment,
  CampaignDetail,
  CampaignSummary,
  DraftData,
  JobEvent,
  JobSnapshot,
  SendSummary,
  Settings,
  Tracking,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new ApiError("Le moteur d'Auto Mail ne répond pas.", 0);
  }
  if (!res.ok) {
    let message = `Erreur ${res.status}`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      /* corps vide */
    }
    throw new ApiError(message, res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

const enc = encodeURIComponent;
const c = (id: string) => `/api/campaigns/${enc(id)}`;

export const api = {
  settings: () => request<Settings>("GET", "/api/settings"),
  saveSettings: (s: Partial<Settings>) => request<Settings>("PUT", "/api/settings", s),
  savePassword: (password: string) => request<Settings>("PUT", "/api/account/password", { password }),
  testAccount: (body: { email?: string; password?: string }) =>
    request<{ ok: boolean; message: string }>("POST", "/api/account/test", body),

  campaigns: () => request<CampaignSummary[]>("GET", "/api/campaigns"),
  campaign: (id: string) => request<CampaignDetail>("GET", c(id)),
  createCampaign: (name: string) => request<CampaignDetail>("POST", "/api/campaigns", { name }),
  renameCampaign: (id: string, name: string) => request<CampaignDetail>("PATCH", c(id), { name }),
  deleteCampaign: (id: string) => request<void>("DELETE", c(id)),
  importCampaign: (file: File, name = "") => {
    const form = new FormData();
    form.append("file", file);
    form.append("name", name);
    return request<CampaignDetail>("POST", "/api/campaigns/import", form);
  },
  saveDraft: (id: string, draft: Partial<DraftData>) => request<CampaignDetail>("PUT", `${c(id)}/draft`, draft),
  addAttachments: (id: string, files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return request<Attachment[]>("POST", `${c(id)}/attachments`, form);
  },
  removeAttachment: (id: string, name: string) =>
    request<Attachment[]>("DELETE", `${c(id)}/attachments/${enc(name)}`),
  openFolder: (id: string) => request<{ ok: boolean }>("POST", `${c(id)}/open-folder`),

  analyze: (id: string, raw: string) => request<Analysis>("POST", `${c(id)}/analyze`, { raw }),
  sendSummary: (id: string) => request<SendSummary>("GET", `${c(id)}/send-summary`),
  testSend: (id: string) => request<{ ok: boolean; message: string }>("POST", `${c(id)}/test-send`),
  startSend: (id: string) => request<JobSnapshot>("POST", `${c(id)}/send`),
  currentJob: () => request<JobSnapshot | null>("GET", "/api/jobs/current"),
  jobLog: (jobId: string) => request<JobEvent[]>("GET", `/api/jobs/${enc(jobId)}/log`),
  controlJob: (jobId: string, action: "pause" | "resume" | "cancel") =>
    request<JobSnapshot>("POST", `/api/jobs/${enc(jobId)}/${action}`),

  tracking: (id: string) => request<Tracking>("GET", `${c(id)}/tracking`),
  editCell: (id: string, email: string, value: string, column = "reponse") =>
    request<{ ok: boolean }>("PATCH", `${c(id)}/tracking`, { email, column, value }),
  exportUrl: (id: string) => `${c(id)}/export`,
  checkReplies: (id: string) =>
    request<{ found: number; updated: string[] }>("POST", `${c(id)}/check-replies`),
};
