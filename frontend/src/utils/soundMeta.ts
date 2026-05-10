import { SoundClass } from "../types/contracts";

export const SOUND_EMOJI: Record<SoundClass, string> = {
  clap: "👏",
  crying: "😢",
  broken_glass: "🪟",
  doorbell: "🔔",
  metal_sound: "🔩",
  alarm: "🚨",
  dog: "🐕",
  scream: "😱",
  knock: "✊",
  phone: "📱",
};

export function soundLabel(soundClass: SoundClass): string {
  return soundClass.replace(/_/g, " ");
}

export function soundEmoji(soundClass: SoundClass): string {
  return SOUND_EMOJI[soundClass];
}
