import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useDraft } from "./useDraft";

describe("useDraft", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("updates instantly and commits once after the debounce", () => {
    const commit = vi.fn();
    const { result } = renderHook(() => useDraft("a", commit, 500));
    act(() => result.current.onChange("ab"));
    act(() => result.current.onChange("abc"));
    expect(result.current.value).toBe("abc");
    expect(commit).not.toHaveBeenCalled();
    act(() => void vi.advanceTimersByTime(500));
    expect(commit).toHaveBeenCalledTimes(1);
    expect(commit).toHaveBeenCalledWith("abc");
  });

  it("flushes immediately on blur and does not double-commit", () => {
    const commit = vi.fn();
    const { result } = renderHook(() => useDraft("a", commit, 500));
    act(() => result.current.onChange("x"));
    act(() => result.current.flush());
    act(() => void vi.advanceTimersByTime(1000));
    expect(commit).toHaveBeenCalledTimes(1);
  });

  it("commits a pending edit on unmount", () => {
    const commit = vi.fn();
    const { result, unmount } = renderHook(() => useDraft("a", commit, 500));
    act(() => result.current.onChange("pending"));
    unmount();
    expect(commit).toHaveBeenCalledWith("pending");
  });

  it("adopts upstream changes when idle but not mid-edit", () => {
    const commit = vi.fn();
    const { result, rerender } = renderHook(({ v }) => useDraft(v, commit, 500), { initialProps: { v: "one" } });
    rerender({ v: "two" });
    expect(result.current.value).toBe("two");
    act(() => result.current.onChange("typing"));
    rerender({ v: "server-echo" });
    expect(result.current.value).toBe("typing");
  });
});
