export type ThemePalette = {
  value: string;
  label: string;
  mode: "dark" | "light";
  swatches: [string, string, string];
};

export const DEFAULT_THEME = "samurai";

export const THEME_PALETTES: ThemePalette[] = [
  { value: "samurai", label: "Red Samurai", mode: "dark", swatches: ["#ef4444", "#f59e0b", "#170505"] },
  { value: "sakura", label: "Sakura Mist", mode: "light", swatches: ["#e11d48", "#f9a8d4", "#fff1f2"] },
  { value: "ocean", label: "Ocean Blue", mode: "dark", swatches: ["#38bdf8", "#22d3ee", "#06131e"] },
  { value: "forest", label: "Forest Jade", mode: "dark", swatches: ["#22c55e", "#84cc16", "#08140d"] },
  { value: "sunset", label: "Sunset Ember", mode: "dark", swatches: ["#fb923c", "#f43f5e", "#1d0b05"] },
  { value: "royal", label: "Royal Indigo", mode: "dark", swatches: ["#6366f1", "#a855f7", "#0d0821"] },
  { value: "emerald", label: "Emerald Light", mode: "light", swatches: ["#059669", "#14b8a6", "#ecfdf5"] },
  { value: "amber", label: "Amber Sand", mode: "light", swatches: ["#d97706", "#f59e0b", "#fff7ed"] },
  { value: "grape", label: "Grape Velvet", mode: "dark", swatches: ["#a855f7", "#ec4899", "#17081f"] },
  { value: "mint", label: "Mint Breeze", mode: "light", swatches: ["#0d9488", "#06b6d4", "#f0fdfa"] },
  { value: "monochrome", label: "Monochrome", mode: "light", swatches: ["#111827", "#6b7280", "#f3f4f6"] },
  { value: "cyber", label: "Cyber Neon", mode: "dark", swatches: ["#06b6d4", "#22c55e", "#040b13"] },
];

export const THEME_PALETTE_MAP = new Map(THEME_PALETTES.map((palette) => [palette.value, palette]));

