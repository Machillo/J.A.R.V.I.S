import { Capacitor } from "@capacitor/core";

const PRODUCTION_API_URL = "https://jarvis-backend-152f.onrender.com";

export const API_URL = Capacitor.isNativePlatform()
  ? import.meta.env.VITE_NATIVE_API_URL || PRODUCTION_API_URL
  : import.meta.env.VITE_API_URL ||
    (import.meta.env.DEV ? "http://127.0.0.1:8000" : PRODUCTION_API_URL);
