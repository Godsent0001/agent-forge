import { describe, expect, it } from "vitest";
import { isSimulatedText } from "./simulated";

describe("isSimulatedText", () => {
  it("flags the test runner's echo", () => {
    expect(isSimulatedText("FakeRunner completed: Help me investigate a bug.")).toBe(true);
  });
  it("does not flag real replies or empty values", () => {
    expect(isSimulatedText("Here is my analysis of the bug…")).toBe(false);
    expect(isSimulatedText("Note: FakeRunner completed: is a string I might discuss")).toBe(false);
    expect(isSimulatedText(null)).toBe(false);
    expect(isSimulatedText(undefined)).toBe(false);
  });
});
