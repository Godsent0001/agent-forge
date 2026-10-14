import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Local editing buffer for a text field that is persisted elsewhere (e.g. PATCHed to the API).
 *
 * - Typing is instant (no waiting for the server echo), so characters are never dropped.
 * - The change is committed after `delay` ms of inactivity, on blur, and on unmount.
 * - Upstream value changes are adopted unless the user is mid-edit.
 *
 * Mount the field with `key={entityId}` so that switching entities flushes the pending edit
 * to the *old* entity (via the unmount flush) instead of leaking it into the new one.
 */
export function useDraft(value: string, onCommit: (next: string) => void, delay = 600) {
  const [draft, setDraft] = useState(value);
  const latest = useRef(value);
  const dirty = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const commitRef = useRef(onCommit);
  commitRef.current = onCommit;

  useEffect(() => {
    if (!dirty.current) {
      setDraft(value);
      latest.current = value;
    }
  }, [value]);

  const flush = useCallback(() => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    if (dirty.current) {
      dirty.current = false;
      commitRef.current(latest.current);
    }
  }, []);

  const onChange = useCallback(
    (next: string) => {
      setDraft(next);
      latest.current = next;
      dirty.current = true;
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(flush, delay);
    },
    [delay, flush],
  );

  useEffect(() => flush, [flush]);

  return { value: draft, onChange, flush };
}
