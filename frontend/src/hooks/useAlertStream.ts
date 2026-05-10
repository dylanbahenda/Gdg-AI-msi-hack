import { listen } from "@tauri-apps/api/event";
import { useEffect, useCallback } from "react";
import { AlertNotification, RawEvent } from "../types/contracts";

/**
 * Subscribes to Tauri events emitted by the Rust backend bridge.
 *
 * Only active when running inside Tauri (window.__TAURI_INTERNALS__ defined).
 */
export function useAlertStream(
  onAlert: (n: AlertNotification) => void,
  onRawEvent: (n: RawEvent) => void,
): void {
  const stableAlert = useCallback(onAlert, []); // eslint-disable-line react-hooks/exhaustive-deps
  const stableRaw = useCallback(onRawEvent, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    // Only subscribe when actually running inside Tauri.
    if (!("__TAURI_INTERNALS__" in window)) return;

    let cancelled = false;
    let unlistenAlert: (() => void) | null = null;
    let unlistenRaw: (() => void) | null = null;

    listen<string>("alert", (event) => {
      if (cancelled) return;
      try {
        const notification: AlertNotification = JSON.parse(event.payload);
        stableAlert(notification);
      } catch {
        console.warn("Received malformed alert payload:", event.payload);
      }
    }).then((fn) => {
      unlistenAlert = fn;
    });

    listen<string>("raw_event", (event) => {
      if (cancelled) return;
      try {
        const notification: RawEvent = JSON.parse(event.payload);
        stableRaw(notification);
      } catch {
        console.warn("Received malformed raw event payload:", event.payload);
      }
    }).then((fn) => {
      unlistenRaw = fn;
    });

    return () => {
      cancelled = true;
      unlistenAlert?.();
      unlistenRaw?.();
    };
  }, [stableAlert, stableRaw]);
}
