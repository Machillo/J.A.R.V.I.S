import { Mic } from "lucide-react";

export default function VoiceButton({ onClick, isListening }) {
  return (
    <button
      type="button"
      className={`voice-button ${isListening ? "listening" : ""}`}
      onClick={onClick}
      aria-label={isListening ? "Detener dictado" : "Hablar con JARVIS"}
      aria-pressed={Boolean(isListening)}
    >
      <Mic size={42} />
    </button>
  );
}