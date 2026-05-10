export type SoundClass =
  | "clap"
  | "crying"
  | "broken_glass"
  | "doorbell"
  | "metal_sound"
  | "alarm"
  | "dog"
  | "scream"
  | "knock"
  | "phone";

export type Priority = "low" | "medium" | "high";

export interface RawEvent {
  channel: "raw_event";
  window_id: number;
  timestamp: number;
  sound_class: SoundClass;
  sed_confidence: number;
  doa_direction_of_arrival: number;
  doa_distance_estimation: number;
}

export interface AlertNotification {
  channel?: "alert";
  timestamp: number;             // unix epoch seconds
  sound_class: SoundClass;
  direction_of_arrival: number;  // 0–359.9°, clockwise from front
  distance_estimation: number;   // metres
  sed_confidence: number;        // 0.0–1.0
  priority: Priority;
  message: string;               // max 80 chars
  duration_s?: number;
  window_count?: number;
}

export type PipelineEvent = AlertNotification | RawEvent;

export interface SystemInfo {
  channel: "system_info";
  mono_fallback: boolean;
}
