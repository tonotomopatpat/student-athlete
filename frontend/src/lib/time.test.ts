import { addDays, clockToMinutes, dayKey, minutesToClock, relativeDay, toNaiveIso } from "./time";

describe("time helpers", () => {
  it("formats naive local ISO without an offset", () => {
    expect(toNaiveIso(new Date(2026, 2, 2, 8, 5))).toBe("2026-03-02T08:05:00");
  });

  it("round-trips clock strings and minutes", () => {
    expect(minutesToClock(6 * 60 + 5)).toBe("06:05");
    expect(clockToMinutes("22:30")).toBe(1350);
    expect(minutesToClock(clockToMinutes("13:45"))).toBe("13:45");
  });

  it("derives stable day keys", () => {
    expect(dayKey("2026-03-02T23:59:00")).toBe("2026-03-02");
  });

  it("labels today and tomorrow", () => {
    const now = new Date(2026, 2, 2, 12);
    expect(relativeDay("2026-03-02T09:00:00", now)).toBe("Today");
    expect(relativeDay("2026-03-03T09:00:00", now)).toBe("Tomorrow");
  });

  it("adds days across month ends", () => {
    expect(dayKey(addDays(new Date(2026, 0, 31), 1))).toBe("2026-02-01");
  });
});
