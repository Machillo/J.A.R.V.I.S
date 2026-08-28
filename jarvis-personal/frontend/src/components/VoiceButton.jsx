import { Mic } from "lucide-react";

export default function VoiceButton({ onClick, isListening }) {
  return (
    <button
      className={`voice-button ${isListening ? "listening" : ""}`}
      onClick={onClick}
    >
      <Mic size={42} />
    </button>
  );
}