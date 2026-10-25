import { describe, expect, it } from "vitest";
import { formatAxisNumber, formatBytes, formatCores, formatSeconds, formatShare } from "./format";

describe("performance formatters", () => {
  it("formats bytes with binary units", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1.5 * 1024 ** 3)).toBe("1.5 GiB");
    expect(formatBytes(null)).toBe("—");
  });

  it("formats seconds at a readable scale", () => {
    expect(formatSeconds(0.025)).toBe("25 ms");
    expect(formatSeconds(30)).toBe("30.0 s");
    expect(formatSeconds(600)).toBe("10.0 min");
    expect(formatSeconds(7200)).toBe("2.0 h");
  });

  it("keeps small axis ticks distinct", () => {
    expect([0, 0.05, 0.1, 0.15, 0.2].map(formatAxisNumber)).toEqual(["0", "0.05", "0.1", "0.15", "0.2"]);
    expect(formatAxisNumber(12.5)).toBe("13");
  });

  it("formats cores and shares", () => {
    expect(formatCores(1.234)).toBe("1.23 cores");
    expect(formatShare(0.42)).toBe("42%");
    expect(formatShare(Number.NaN)).toBe("—");
  });
});
