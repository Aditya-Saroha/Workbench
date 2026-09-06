"use client";

import { useEffect, useState } from "react";

const SESSION_KEY = "mrpl-workbench-session-id";
const SESSION_EVENT = "mrpl-workbench-session-changed";

function createSessionId() {
  return `session-${crypto.randomUUID()}`;
}

export function getSessionId() {
  if (typeof window === "undefined") return "default";
  let sessionId = window.localStorage.getItem(SESSION_KEY);
  if (!sessionId) {
    sessionId = createSessionId();
    window.localStorage.setItem(SESSION_KEY, sessionId);
  }
  return sessionId;
}

export function setSessionId(sessionId: string) {
  window.localStorage.setItem(SESSION_KEY, sessionId);
  window.dispatchEvent(new CustomEvent(SESSION_EVENT, { detail: sessionId }));
}

export function useSessionId() {
  const [sessionId, setSession] = useState("default");

  useEffect(() => {
    const update = () => setSession(getSessionId());
    update();
    window.addEventListener(SESSION_EVENT, update);
    return () => window.removeEventListener(SESSION_EVENT, update);
  }, []);

  return sessionId;
}
