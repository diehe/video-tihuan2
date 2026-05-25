export interface AiSettings {
  apiBaseUrl: string;
  apiKey: string;
  model: string;
}

export const DEFAULT_AI_SETTINGS: AiSettings = {
  apiBaseUrl: "https://api.openai.com/v1",
  apiKey: "",
  model: "gpt-4.1-mini",
};

const STORAGE_KEY = "video-tihuan.ai-settings";

type StorageLike = Pick<Storage, "getItem" | "setItem">;

export function loadAiSettings(storage: StorageLike = window.localStorage): AiSettings {
  try {
    const raw = storage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_AI_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<AiSettings>;
    return {
      apiBaseUrl: typeof parsed.apiBaseUrl === "string" ? parsed.apiBaseUrl : DEFAULT_AI_SETTINGS.apiBaseUrl,
      apiKey: typeof parsed.apiKey === "string" ? parsed.apiKey : DEFAULT_AI_SETTINGS.apiKey,
      model: typeof parsed.model === "string" ? parsed.model : DEFAULT_AI_SETTINGS.model,
    };
  } catch {
    return DEFAULT_AI_SETTINGS;
  }
}

export function saveAiSettings(settings: AiSettings, storage: StorageLike = window.localStorage): void {
  storage.setItem(STORAGE_KEY, JSON.stringify(settings));
}
