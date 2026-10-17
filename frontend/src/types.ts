export type Counts = { total: number; sent: number; errors: number; replies: number };

export type CampaignSummary = {
  id: string;
  name: string;
  created: string;
  updated: string;
  subject: string;
  counts: Counts;
};

export type Mode = "text" | "html" | "visual";

export type DraftData = {
  name: string;
  created: string;
  subject: string;
  mode: Mode;
  text: string;
  html: string;
  recipients_raw: string;
  label: string;
  preview_email: string;
  updated: string;
};

export type Attachment = { name: string; size: number };

export type CampaignDetail = CampaignSummary & {
  draft: DraftData;
  attachments: Attachment[];
  path: string;
};

export type Settings = {
  email: string;
  display_name: string;
  delay_seconds: number;
  theme: "system" | "light" | "dark";
  has_password: boolean;
  data_dir: string;
};

export type RecipientStatus = "new" | "retry" | "sent";

export type Analysis = {
  recipients: { email: string; fields: Record<string, string>; status: RecipientStatus }[];
  invalid: string[];
  duplicates: string[];
  columns: string[];
  counts: {
    valid: number;
    invalid: number;
    duplicates: number;
    already_sent: number;
    retry: number;
    new: number;
    to_send: number;
  };
};

export type SendSummary = {
  count: number;
  retry: number;
  already_sent: number;
  sender: string;
  sender_name: string;
  has_password: boolean;
  label: string;
  subject: string;
  mode: Mode;
  attachments: Attachment[];
  delay_seconds: number;
  estimate_seconds: number;
  over_limit: boolean;
  limit: number;
};

export type JobState = "pending" | "running" | "paused" | "cancelled" | "done" | "failed";

export type JobSnapshot = {
  id: string;
  campaign_id: string;
  state: JobState;
  total: number;
  sent: number;
  errors: number;
  skipped: number;
  current: string;
  label: string;
};

export type JobEvent = {
  seq: number;
  type: "start" | "sent" | "error" | "skipped" | "warning" | "paused" | "resumed" | "label" | "done";
  time: string;
  email?: string;
  message?: string;
  ok?: boolean;
  code?: string;
  count?: number;
  progress: JobSnapshot;
};

export type Tracking = {
  columns: string[];
  rows: Record<string, string>[];
  counts: Counts;
  path: string;
};
