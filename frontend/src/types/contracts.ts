export type SoundClass =
  | "clap"
  | "baby_cry"
  | "broken_glass"
  | "doorbell"
  | "metal_sound"
  | "alarm";

export type Priority = "low" | "medium" | "high";

export interface AlertNotification {
  timestamp: number;             // unix epoch seconds
  sound_class: SoundClass;
  direction_of_arrival: number;  // 0–359.9°, clockwise from front
  distance_estimation: number;   // metres
  sed_confidence: number;        // 0.0–1.0
  priority: Priority;
  message: string;               // max 80 chars
}
