import { describe, expect, it } from "vitest";
import { DEFAULT_AI_SETTINGS, loadAiSettings, saveAiSettings } from "./settings";

describe("AI settings persistence", () => {
  it("loads defaults when storage is empty", () => {
    const storage = new MapStorage();

    expect(loadAiSettings(storage)).toEqual(DEFAULT_AI_SETTINGS);
  });

  it("saves and reloads API settings", () => {
    const storage = new MapStorage();
    const settings = {
      apiBaseUrl: "https://api.example.com/v1",
      apiKey: "sk-test",
      model: "vision-model",
    };

    saveAiSettings(settings, storage);

    expect(loadAiSettings(storage)).toEqual(settings);
  });
});

class MapStorage implements Pick<Storage, "getItem" | "setItem"> {
  private readonly values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}
