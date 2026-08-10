import { create } from "zustand";
import type { FeedbackCapture, FeedbackCategory } from "../feedback";
export type ConsoleFilter = "error" | "warn" | "all";

type FeedbackSettings = {
  includeMetadata: boolean;
  includeConsole: boolean;
  consoleLevel: ConsoleFilter;
  consoleLimit: number;
  includeNetwork: boolean;
  networkLimit: number;
};

type FeedbackState = FeedbackSettings & {
  isOpen: boolean;
  isElementSelecting: boolean;
  hideTrigger: boolean;
  title: string;
  description: string;
  category: FeedbackCategory;
  rating: number | null;
  captures: FeedbackCapture[];
  open: () => void;
  close: () => void;
  reset: () => void;
  setElementSelecting: (value: boolean) => void;
  setHideTrigger: (value: boolean) => void;
  setTitle: (value: string) => void;
  setDescription: (value: string) => void;
  setCategory: (value: FeedbackCategory) => void;
  setRating: (value: number | null) => void;
  addCapture: (capture: Omit<FeedbackCapture, "id">) => void;
  removeCapture: (id: string) => void;
  setSetting: <Key extends keyof FeedbackSettings>(key: Key, value: FeedbackSettings[Key]) => void;
};

const settingsKey = "rtsai-feedback-settings";
const defaults: FeedbackSettings = {
  includeMetadata: true,
  includeConsole: false,
  consoleLevel: "error",
  consoleLimit: 30,
  includeNetwork: false,
  networkLimit: 20,
};

function loadSettings(): FeedbackSettings {
  if (typeof window === "undefined") return defaults;
  try {
    const parsed = JSON.parse(localStorage.getItem(settingsKey) || "{}") as Partial<FeedbackSettings>;
    return {
      includeMetadata: parsed.includeMetadata ?? defaults.includeMetadata,
      includeConsole: parsed.includeConsole ?? defaults.includeConsole,
      consoleLevel: ["error", "warn", "all"].includes(parsed.consoleLevel || "") ? parsed.consoleLevel as ConsoleFilter : defaults.consoleLevel,
      consoleLimit: Math.min(100, Math.max(5, Number(parsed.consoleLimit) || defaults.consoleLimit)),
      includeNetwork: parsed.includeNetwork ?? defaults.includeNetwork,
      networkLimit: Math.min(50, Math.max(5, Number(parsed.networkLimit) || defaults.networkLimit)),
    };
  } catch {
    return defaults;
  }
}

function persistSettings(settings: FeedbackSettings) {
  if (typeof window !== "undefined") localStorage.setItem(settingsKey, JSON.stringify(settings));
}

let captureId = 0;

export const useFeedbackStore = create<FeedbackState>((set, get) => ({
  ...loadSettings(),
  isOpen: false,
  isElementSelecting: false,
  hideTrigger: false,
  title: "",
  description: "",
  category: "General",
  rating: null,
  captures: [],
  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false, isElementSelecting: false }),
  reset: () => set({ isOpen: false, isElementSelecting: false, title: "", description: "", category: "General", rating: null, captures: [] }),
  setElementSelecting: (value) => set({ isElementSelecting: value, isOpen: !value }),
  setHideTrigger: (value) => set({ hideTrigger: value }),
  setTitle: (value) => set({ title: value }),
  setDescription: (value) => set({ description: value }),
  setCategory: (value) => set({ category: value }),
  setRating: (value) => set({ rating: value }),
  addCapture: (capture) => set((state) => ({ captures: [...state.captures, { ...capture, id: `cap_${++captureId}_${Date.now()}` }].slice(-10) })),
  removeCapture: (id) => set((state) => ({ captures: state.captures.filter((capture) => capture.id !== id) })),
  setSetting: (key, value) => {
    set({ [key]: value } as Pick<FeedbackState, typeof key>);
    const state = get();
    persistSettings({
      includeMetadata: state.includeMetadata,
      includeConsole: state.includeConsole,
      consoleLevel: state.consoleLevel,
      consoleLimit: state.consoleLimit,
      includeNetwork: state.includeNetwork,
      networkLimit: state.networkLimit,
    });
  },
}));
