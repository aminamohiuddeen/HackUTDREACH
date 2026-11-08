import { describe, expect, it } from "vitest";
import { approvedRole, authMessage } from "./access";

describe("REACH approved roles", () => {
  it("permits the securely retrieved Administrator role", () => { expect(approvedRole(["administrator"])).toBe("administrator"); });
  it("permits the securely retrieved First Responder role", () => { expect(approvedRole(["first_responder"])).toBe("first_responder"); });
  it("denies users without an approved role", () => { expect(approvedRole([])).toBeNull(); expect(approvedRole(["user", "admin"])).toBeNull(); });
});

describe("authentication errors", () => {
  it("never exposes provider error details", () => { expect(authMessage({ message: "private provider details" })).not.toContain("private provider details"); });
});