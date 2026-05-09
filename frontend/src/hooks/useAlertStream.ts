import { listen } from "@tauri-apps/api/event";
import { useEffect, useCallback } from "react";
import { AlertNotification } from "../types/contracts";

/**
 * Subscribes to Tauri "alert" events emitted by the Rust sidecar bridge.
 * Calls onAlert for every incoming AlertNotification.
 *
 * Only active when running inside Tauri (window.__TAURI_INTERNALS__ defined).
 */
export function useAlertStream(onAlert: (n: AlertNotification) => void): void {
  const stable = useCallback(onAlert, []); // eslint-disable-line

  useEffect(() => {
    // Only subscribe when actually running inside Tauri.
    if (!("__TAURI_INTERNALS__" in window)) return;

    let cancelled = false;
    let unlisten: (() => void) | null = null;

    listen<string>("alert", (event) => {
      if (cancelled) return;
      try {
        const notification: AlertNotification = JSON.parse(event.payload);
        stable(notification);
      } catch {
        console.warn("Received malformed alert payload:", event.payload);
      }
    }).then((fn) => {
      unlisten = fn;
    });

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [stable]);
}
