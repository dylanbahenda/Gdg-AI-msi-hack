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

// Maps each sound class to a custom illustration in /public/img/.
// null means no custom image → fall back to emoji.
export const SOUND_IMAGE: Record<SoundClass, string | null> = {
  alarm:        "/img/alarm.jpg",
  broken_glass: "/img/brokenglass.jpg",
  clap:         "/img/clap.jpg",
  crying:       "/img/cry.jpg",
  dog:          "/img/dog.jpg",
  doorbell:     "/img/boy.jpg",
  knock:        "/img/knock.jpg",
  metal_sound:  "/img/metal.jpg",
  scream:       "/img/scream.jpg",
  phone:        null,
};

export function soundLabel(soundClass: SoundClass): string {
  return soundClass.replace(/_/g, " ");
}

export function soundEmoji(soundClass: SoundClass): string {
  return SOUND_EMOJI[soundClass];
}

export function soundImage(soundClass: SoundClass): string | null {
  return SOUND_IMAGE[soundClass];
}
