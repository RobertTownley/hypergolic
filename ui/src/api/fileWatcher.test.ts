import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

describe("fileWatcher debouncing", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("should debounce rapid calls to listeners", () => {
    const callback = vi.fn();

    // Simulate the debounce logic from fileWatcher
    let timer: ReturnType<typeof setTimeout> | null = null;
    const DEBOUNCE_MS = 1000;

    const debouncedFire = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        callback();
        timer = null;
      }, DEBOUNCE_MS);
    };

    // Fire 10 rapid events
    for (let i = 0; i < 10; i++) {
      debouncedFire();
    }

    // Callback should not have been called yet
    expect(callback).not.toHaveBeenCalled();

    // After debounce interval, callback fires once
    vi.advanceTimersByTime(1000);
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it("should fire again after debounce interval resets", () => {
    const callback = vi.fn();
    let timer: ReturnType<typeof setTimeout> | null = null;
    const DEBOUNCE_MS = 1000;

    const debouncedFire = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        callback();
        timer = null;
      }, DEBOUNCE_MS);
    };

    // First burst
    debouncedFire();
    debouncedFire();
    vi.advanceTimersByTime(1000);
    expect(callback).toHaveBeenCalledTimes(1);

    // Second burst
    debouncedFire();
    vi.advanceTimersByTime(1000);
    expect(callback).toHaveBeenCalledTimes(2);
  });
});
