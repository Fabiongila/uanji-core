import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { api } from "@/api/client";
import type { AppSettings, Appearance } from "@/api/types";

export const DEFAULT_APPEARANCE: Appearance = {
  theme: "uanji-dark",
  accent: "cyan",
  density: "comfortable",
  font_scale: 100,
  sidebar: "left",
  layout_mode: "custom",
  cards: [],
};

export function appearanceOf(settings: Partial<AppSettings> | undefined): Appearance {
  return { ...DEFAULT_APPEARANCE, ...(settings?.appearance ?? {}) };
}

/** Aplica tema, cor de destaque e escala ao documento (variáveis CSS; sem re-render dos componentes). */
export function useApplyAppearance(a: Appearance) {
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = a.theme;
    root.dataset.accent = a.accent;
    root.dataset.density = a.density;
    // Densidade compacta = 92 % do tamanho; combinada com a escala do texto escolhida.
    const zoom = (a.font_scale / 100) * (a.density === "compact" ? 0.92 : 1);
    root.style.setProperty("--ui-zoom", String(Math.round(zoom * 100) / 100));
  }, [a.theme, a.accent, a.density, a.font_scale]);
}

/** Área da aplicação a partir do caminho (para o modo adaptativo do painel). */
export function areaOf(pathname: string): string {
  const seg = pathname.split("/")[1] ?? "";
  return seg === "" ? "home" : seg.replace(/[^a-z-]/g, "");
}

/** Regista localmente as áreas visitadas (uma vez por mudança de página). */
export function useUsageTracking(enabled: boolean) {
  const { pathname } = useLocation();
  useEffect(() => {
    if (!enabled) return;
    const area = areaOf(pathname);
    if (!area) return;
    const t = window.setTimeout(() => void api.post("/api/usage", { area }).catch(() => undefined), 1500);
    return () => window.clearTimeout(t);
  }, [pathname, enabled]);
}
