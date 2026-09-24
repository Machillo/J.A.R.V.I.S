import { useState } from "react";

// Drops re-entrant calls while a save is in flight. A double tap on "Guardar" fires
// two submit events before React re-renders a disabled button, so the guard is a
// plain flag, not state; `onPendingChange` only drives the visual disabled state.
export function createSingleFlight(onPendingChange = () => {}) {
  let inFlight = false;
  return (handler) => async (...args) => {
    if (inFlight) {
      args[0]?.preventDefault?.();
      return undefined;
    }
    inFlight = true;
    onPendingChange(true);
    try {
      return await handler(...args);
    } finally {
      inFlight = false;
      onPendingChange(false);
    }
  };
}

export function useSingleFlight() {
  const [pending, setPending] = useState(false);
  // Created once per component; the flag lives in its closure across renders.
  const [once] = useState(() => createSingleFlight(setPending));
  return [once, pending];
}
