import { useEffect } from "react";
import { api, isTauri } from "@/api/client";
import type { NotificationItem } from "@/api/types";

/**
 * Notificações nativas do macOS (apenas dentro do Tauri e se activadas nas Definições).
 * Consulta o backend a cada 60 s — sem polling agressivo.
 */
export function NativeNotifications() {
  useEffect(() => {
    if (!isTauri()) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const pending = await api.get<NotificationItem[]>("/api/notifications/native");
        if (!pending.length || cancelled) return;
        const mod = await import("@tauri-apps/plugin-notification");
        let granted = await mod.isPermissionGranted();
        if (!granted) granted = (await mod.requestPermission()) === "granted";
        if (!granted) return;
        for (const n of pending) mod.sendNotification({ title: n.title, body: n.body || undefined });
        await api.post("/api/notifications/native/sent", { ids: pending.map((n) => n.id) });
      } catch {
        /* o estado do backend é mostrado na barra superior */
      }
    };
    const id = window.setInterval(tick, 60_000);
    void tick();
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);
  return null;
}
