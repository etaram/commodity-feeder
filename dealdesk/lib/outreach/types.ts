// Types for the systematic outreach engine (spec phase 7). Server side only.
// Nothing in this module reaches a real recipient: the only transport is TestTransport (lib/outreach/transport.ts).

export type Channel = "email" | "linkedin";

export type CampaignStatus = "draft" | "authorized" | "running" | "paused" | "cancelled" | "stopped";

export type AccountStage =
  | "identified" | "reviewed" | "campaign_eligible" | "contact_confirmed" | "outreach_authorized"
  | "contacted" | "response_classified" | "qualified" | "nurture" | "closed";

// An approved claim: the only factual statements a message may make. source makes it traceable (URL, document, deal id).
export type Claim = { id: string; text: string; source: string };

// A message variant. step 0 is the first message, step n the n-th follow-up. Placeholders: {{first_name|there}},
// {{company}}, {{claim:c1}}, {{offer}}, {{sender_name}}, {{sender_org}} and the plan's personalization fields.
export type Template = { id: string; step: number; channel: Channel; kind: "email" | "connect" | "message"; subject: string; body: string };

export type Sender = { name: string; email: string; org: string; title: string; address: string };

export type CampaignPlan = {
  name: string; client: string; segment: string; objective: string;
  target_profile: string; exclusions: string[];
  owner: string; sender: Sender; channel: Channel;
  claims: Claim[]; offer: string; attachments: { name: string; ref: string }[];
  templates: Template[]; personalization_fields: string[];
  cadence: { gap_days: number[] }; follow_up_limit: number;
  volume: { per_hour: number; per_day: number; max_accounts: number; budget: string };
  research_tasks: string[]; review_dates: string[]; stop_conditions: string[]; success_metrics: string[];
  auto_stop: { max_hard_bounces: number; max_opt_outs: number };
  recent_contact_days: number;
  opt_out_line: string; linkedin_opt_out_line: string;
  adapt_wording: boolean;
  pilot_review_note: string;
};

// What an admin authorized: who, when, the hash of the material scope, and the exact audience (account id|email).
export type Authorization = { by: string; at: string; scope_hash: string; plan_hash: string; audience: string[] };

export type Campaign = {
  id: string; ws: string; status: CampaignStatus; status_reason: string;
  plan: CampaignPlan; authorization: Authorization | null;
  created_by: string; created_at: string; updated_at: string;
};

export type Account = {
  id: string; ws: string; campaign_id: string; stage: AccountStage; stage_reason: string;
  company: string; contact_name: string; first_name: string; last_name: string; title: string;
  email: string; linkedin_url: string; country: string;
  contact_source: string; // where the contact detail came from (never invented)
  conflict: boolean; // set by a human or another module when the account is in a conflicting deal or campaign
  fields: Record<string, string>; notes: string; updated_at: string;
};

export type OutboxStatus = "queued" | "sending" | "sent" | "cancelled" | "failed" | "needs_review";

export type OutboxItem = {
  id: string; ws: string; campaign_id: string; account_id: string; step: number; idem_key: string;
  status: OutboxStatus; reason: string; due_at: string; attempts: number; last_error: string;
  to: string; from_email: string; from_name: string; subject: string; body: string;
  attachments: { name: string; ref: string }[]; claims_used: string[]; template_id: string;
  plan_hash: string; adapted: { subject: string; body: string } | null;
  created_at: string; created_by: string; sent_at: string; provider_id: string; transport: string;
};

export type ReplyCategory =
  | "opt_out" | "hard_bounce" | "soft_bounce" | "out_of_office"
  | "interested" | "meeting_booked" | "question" | "referral" | "not_interested" | "needs_human";

export type LinkedInTask = {
  id: string; ws: string; campaign_id: string; account_id: string;
  kind: "prospect" | "connect" | "message";
  status: "open" | "done" | "skipped";
  profile_url: string; company: string; contact_name: string; draft: string;
  interaction: string; outcome: string; note: string; done_by: string; done_at: string; created_at: string;
};
