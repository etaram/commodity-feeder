import { defaultClassifyModel } from "./classify";
import { defaultModel } from "./draft";
import type { Deps } from "./outbox";
import { sheetsStore } from "./store-sheets";
import { getTransport } from "./transport";

// Production wiring for the API routes and the cron: engine-sheet storage, the test transport (the only one),
// and the bounded model hooks. Tests build their own Deps with MemoryStore and TestTransport.
export function routeDeps(): Deps {
  return { store: sheetsStore(), transport: getTransport(), now: () => Date.now(), adaptModel: defaultModel, classifyModel: defaultClassifyModel };
}

export const outreachEnabled = () => process.env.OUTREACH_ENABLED === "1";
