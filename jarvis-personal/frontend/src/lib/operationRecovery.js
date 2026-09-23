import { API_URL } from "./apiUrl";
import { authenticatedFetch } from "./authenticatedFetch";
import { supabase } from "./supabase";

const QUEUE_PREFIX = "dincr:operation-queue:v1:";
const MAX_OPERATIONS = 20;
const MAX_BODY_BYTES = 32 * 1024;
const MAX_AGE_MS = 24 * 60 * 60 * 1000;
const RECOVERABLE_METHODS = new Set(["POST", "PUT", "PATCH"]);
const RECOVERABLE_PATH = /^\/user-product\/(?:financial-situation|finance\/(?:income|expenses|debts)(?:\/[^/]+(?:\/payments)?)?|goals(?:\/[^/]+(?:\/contributions)?)?|savings-plans(?:\/[^/]+(?:\/contributions)?)?|transactions|basic\/(?:budget|recurring(?:\/[^/]+)?))\/?$/;
let flushing = false;

const operationId = () => `op_${globalThis.crypto?.randomUUID?.().replaceAll("-", "")
  || `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`}`;

const activeUserId = async () => {
  const result = await supabase.auth.getSession();
  return result?.data?.session?.user?.id || "";
};

const queueKey = (userId) => `${QUEUE_PREFIX}${userId}`;
const purgeExpiredQueues = () => {
  const cutoff = Date.now() - MAX_AGE_MS;
  for (let index = window.localStorage.length - 1; index >= 0; index -= 1) {
    const key = window.localStorage.key(index);
    if (!key?.startsWith(QUEUE_PREFIX)) continue;
    try {
      const parsed = JSON.parse(window.localStorage.getItem(key) || "[]");
      const current = Array.isArray(parsed)
        ? parsed.filter((item) => Number(item.created_at || 0) >= cutoff)
        : [];
      if (current.length) window.localStorage.setItem(key, JSON.stringify(current.slice(-MAX_OPERATIONS)));
      else window.localStorage.removeItem(key);
    } catch {
      window.localStorage.removeItem(key);
    }
  }
};
const readQueue = (userId) => {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(queueKey(userId)) || "[]");
    const cutoff = Date.now() - MAX_AGE_MS;
    return Array.isArray(parsed) ? parsed.filter((item) => Number(item.created_at || 0) >= cutoff) : [];
  } catch {
    return [];
  }
};

const emitQueue = (items) => window.dispatchEvent(new CustomEvent("dincr:operation-queue-changed", {
  detail: { pending: items.length },
}));

const writeQueue = (userId, items) => {
  const next = items.slice(-MAX_OPERATIONS);
  window.localStorage.setItem(queueKey(userId), JSON.stringify(next));
  emitQueue(next);
};

const removeOperation = (userId, id) => {
  const next = readQueue(userId).filter((item) => item.id !== id);
  writeQueue(userId, next);
  return next;
};

const pathFromUrl = (url) => new URL(url, window.location.origin).pathname;
const isRecoverable = (path, options) => {
  const method = String(options.method || "GET").toUpperCase();
  const contentType = String(options.headers?.["Content-Type"] || options.headers?.["content-type"] || "");
  return RECOVERABLE_METHODS.has(method)
    && RECOVERABLE_PATH.test(path)
    && contentType.includes("application/json")
    && typeof options.body === "string"
    && new TextEncoder().encode(options.body).length <= MAX_BODY_BYTES;
};

const requestOptions = (operation) => ({
  method: operation.method,
  headers: {
    "Content-Type": "application/json",
    "X-Request-ID": operation.id,
    "X-Idempotency-Key": operation.id,
  },
  body: operation.body,
});

export async function getPendingOperationCount() {
  purgeExpiredQueues();
  const userId = await activeUserId();
  if (!userId) return 0;
  const queue = readQueue(userId);
  writeQueue(userId, queue);
  return queue.length;
}

export async function recoverableFetch(url, options = {}) {
  const path = pathFromUrl(url);
  if (!isRecoverable(path, options)) return authenticatedFetch(url, options);

  const userId = await activeUserId();
  if (!userId) return authenticatedFetch(url, options);
  purgeExpiredQueues();
  const operation = {
    id: operationId(),
    path,
    method: String(options.method).toUpperCase(),
    body: options.body,
    created_at: Date.now(),
    attempts: 0,
  };
  writeQueue(userId, [...readQueue(userId), operation]);

  try {
    const response = await authenticatedFetch(url, { ...options, ...requestOptions(operation) });
    const processing = response.headers.get("X-Idempotency-Status") === "processing";
    if (response.ok || (response.status < 500 && !processing)) removeOperation(userId, operation.id);
    return response;
  } catch (error) {
    error.dincrOperationQueued = true;
    throw error;
  }
}

export async function flushPendingOperations() {
  if (flushing || !navigator.onLine) return { recovered: 0, pending: null };
  const userId = await activeUserId();
  if (!userId) return { recovered: 0, pending: 0 };
  purgeExpiredQueues();
  flushing = true;
  let recovered = 0;
  try {
    let queue = readQueue(userId);
    writeQueue(userId, queue);
    for (const operation of [...queue]) {
      try {
        const response = await authenticatedFetch(`${API_URL}${operation.path}`, requestOptions(operation));
        const processing = response.headers.get("X-Idempotency-Status") === "processing";
        if (response.ok) {
          queue = removeOperation(userId, operation.id);
          recovered += 1;
          window.dispatchEvent(new CustomEvent("dincr:operation-recovered", {
            detail: { path: operation.path, pending: queue.length },
          }));
          continue;
        }
        if (response.status < 500 && !processing) {
          queue = removeOperation(userId, operation.id);
          window.dispatchEvent(new CustomEvent("dincr:operation-recovery-failed", {
            detail: { path: operation.path, status: response.status, pending: queue.length },
          }));
          continue;
        }
        break;
      } catch {
        break;
      }
    }
    return { recovered, pending: queue.length };
  } finally {
    flushing = false;
  }
}
