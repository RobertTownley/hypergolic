import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ToolParams } from "./ToolParams";

describe("ToolParams", () => {
  it("renders enum values for a nullable enum (anyOf enum + null)", () => {
    render(
      <ToolParams
        schema={{
          properties: {
            model_tier: {
              anyOf: [
                { enum: ["Low", "Medium", "High", "Extra High"], type: "string" },
                { type: "null" },
              ],
              description: "Defaults to your tier",
            },
          },
        }}
      />,
    );
    expect(
      screen.getByText('"Low" | "Medium" | "High" | "Extra High"'),
    ).toBeTruthy();
  });

  it("renders enum values for a plain enum property", () => {
    render(
      <ToolParams
        schema={{
          required: ["role"],
          properties: {
            role: { enum: ["worker", "researcher"], type: "string" },
          },
        }}
      />,
    );
    expect(screen.getByText('"worker" | "researcher"')).toBeTruthy();
  });

  it("renders enum values for an array of enums", () => {
    render(
      <ToolParams
        schema={{
          properties: {
            ids: { type: "array", items: { enum: ["a", "b"], type: "string" } },
          },
        }}
      />,
    );
    expect(screen.getByText('("a" | "b")[]')).toBeTruthy();
  });
});
