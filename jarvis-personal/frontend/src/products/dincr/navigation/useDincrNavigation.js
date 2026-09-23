import { useCallback, useEffect, useRef, useState } from "react";
import { App as CapacitorApp } from "@capacitor/app";
import { Capacitor } from "@capacitor/core";

const STATE_KEY = "dincrNavigation";
const EDGE_START_PX = 28;
const SWIPE_DISTANCE_PX = 84;

export function useDincrBackHandler(handler, enabled = true) {
  const handlerRef = useRef(handler);
  useEffect(() => { handlerRef.current = handler; }, [handler]);
  useEffect(() => {
    if (!enabled) return undefined;
    const consume = (event) => {
      event.preventDefault();
      handlerRef.current?.();
    };
    window.addEventListener("dincr:native-back", consume);
    return () => window.removeEventListener("dincr:native-back", consume);
  }, [enabled]);
}

const navigationState = (page, depth) => ({
  ...(window.history.state || {}),
  [STATE_KEY]: { page, depth },
});

export default function useDincrNavigation(initialPage = "overview") {
  const [page, setPage] = useState(initialPage);
  const pageRef = useRef(initialPage);
  const depthRef = useRef(0);

  const applyPage = useCallback((nextPage) => {
    pageRef.current = nextPage;
    setPage(nextPage);
  }, []);

  const navigate = useCallback((nextPage, { replace = false } = {}) => {
    if (!nextPage || nextPage === pageRef.current) return;
    if (replace) {
      window.history.replaceState(navigationState(nextPage, depthRef.current), "");
    } else {
      depthRef.current += 1;
      window.history.pushState(navigationState(nextPage, depthRef.current), "");
    }
    applyPage(nextPage);
  }, [applyPage]);

  const back = useCallback(() => {
    const event = new CustomEvent("dincr:native-back", { cancelable: true });
    if (!window.dispatchEvent(event)) return true;
    if (depthRef.current > 0) {
      window.history.back();
      return true;
    }
    return false;
  }, []);

  useEffect(() => {
    const existing = window.history.state?.[STATE_KEY];
    if (existing?.page) {
      depthRef.current = Number(existing.depth || 0);
      applyPage(existing.page);
    } else {
      window.history.replaceState(navigationState(initialPage, 0), "");
    }
    const onPopState = (event) => {
      const state = event.state?.[STATE_KEY];
      if (!state?.page) return;
      depthRef.current = Math.max(0, Number(state.depth || 0));
      applyPage(state.page);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [applyPage, initialPage]);

  useEffect(() => {
    if (!Capacitor.isNativePlatform() || Capacitor.getPlatform() !== "android") return undefined;
    let listener;
    CapacitorApp.addListener("backButton", () => {
      if (!back()) CapacitorApp.minimizeApp();
    }).then((handle) => { listener = handle; });
    return () => listener?.remove();
  }, [back]);

  useEffect(() => {
    if (!Capacitor.isNativePlatform() || Capacitor.getPlatform() !== "ios") return undefined;
    let start = null;
    let tracking = false;
    const onTouchStart = (event) => {
      const touch = event.touches[0];
      tracking = Boolean(touch && touch.clientX <= EDGE_START_PX && depthRef.current > 0);
      start = tracking ? { x: touch.clientX, y: touch.clientY } : null;
    };
    const onTouchMove = (event) => {
      if (!tracking || !start) return;
      const touch = event.touches[0];
      if (touch && touch.clientX > start.x && Math.abs(touch.clientY - start.y) < 72) event.preventDefault();
    };
    const onTouchEnd = (event) => {
      if (!tracking || !start) return;
      const touch = event.changedTouches[0];
      const horizontal = touch ? touch.clientX - start.x : 0;
      const vertical = touch ? Math.abs(touch.clientY - start.y) : Infinity;
      tracking = false;
      start = null;
      if (horizontal >= SWIPE_DISTANCE_PX && vertical < 72) back();
    };
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: false });
    window.addEventListener("touchend", onTouchEnd, { passive: true });
    return () => {
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onTouchEnd);
    };
  }, [back]);

  return { page, navigate, back };
}
