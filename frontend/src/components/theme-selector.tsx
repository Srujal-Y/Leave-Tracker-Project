"use client";

import { Palette } from "lucide-react";
import { useTheme } from "next-themes";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { DEFAULT_THEME, THEME_PALETTES } from "@/lib/theme-palettes";

type ThemeSelectorProps = {
  compact?: boolean;
  className?: string;
};

export function ThemeSelector({ compact = false, className }: ThemeSelectorProps) {
  const { theme, setTheme } = useTheme();
  const selectedTheme = theme || DEFAULT_THEME;

  return (
    <div className={cn("flex items-center gap-2", className)}>
      {!compact ? <span className="text-xs text-muted-foreground">Theme</span> : null}
      <Select value={selectedTheme} onValueChange={(value) => setTheme(value)}>
        <SelectTrigger className={cn(compact ? "h-8 w-[170px]" : "w-[220px]")}>
          <div className="flex items-center gap-2">
            <Palette className="h-4 w-4 text-muted-foreground" />
            <SelectValue placeholder="Choose theme" />
          </div>
        </SelectTrigger>
        <SelectContent>
          {THEME_PALETTES.map((palette) => (
            <SelectItem key={palette.value} value={palette.value}>
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1">
                  {palette.swatches.map((swatch) => (
                    <span
                      key={swatch}
                      className="inline-block h-2.5 w-2.5 rounded-full border border-black/20"
                      style={{ backgroundColor: swatch }}
                    />
                  ))}
                </div>
                <span>{palette.label}</span>
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
