import { AlertNotification } from "../types/contracts";

const MOCK_EVENTS: AlertNotification[] = [
  { timestamp: 0, sound_class: "baby_cry",     direction_of_arrival: 45,  distance_estimation: 2.1, sed_confidence: 0.91, priority: "high",   message: "Baby cry detected \u2014 check immediately" },
  { timestamp: 0, sound_class: "doorbell",     direction_of_arrival: 315, distance_estimation: 4.5, sed_confidence: 0.78, priority: "low",    message: "Doorbell at 315\u00b0" },
  { timestamp: 0, sound_class: "broken_glass", direction_of_arrival: 180, distance_estimation: 1.2, sed_confidence: 0.85, priority: "high",   message: "Breaking glass detected \u2014 check area" },
  { timestamp: 0, sound_class: "alarm",        direction_of_arrival: 90,  distance_estimation: 3.0, sed_confidence: 0.95, priority: "high",   message: "Alarm sounding \u2014 take action" },
  { timestamp: 0, sound_class: "metal_sound",  direction_of_arrival: 270, distance_estimation: 2.8, sed_confidence: 0.70, priority: "medium", message: "Metal sound detected nearby" },
  { timestamp: 0, sound_class: "clap",         direction_of_arrival: 0,   distance_estimation: 1.5, sed_confidence: 0.65, priority: "low",    message: "Clap detected \u2014 possible noise" },
];

/** Emits a fake AlertNotification every 3.5 s. Returns a cleanup function. */
export function startMockFeed(onAlert: (n: AlertNotification) => void): () => void {
  let i = 0;
  const id = setInterval(() => {
    onAlert({ ...MOCK_EVENTS[i % MOCK_EVENTS.length], timestamp: Date.now() / 1000 });
    i++;
  }, 3500);
  return () => clearInterval(id);
}
