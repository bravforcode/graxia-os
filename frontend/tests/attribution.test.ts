import { beforeEach, describe, expect, it } from "vitest";
import {
  captureAttribution,
  getAttribution,
  getAttributionEventFields,
} from "../src/lib/attribution";

describe("organic attribution", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    window.history.replaceState({}, "", "/store");
  });

  it("keeps first touch while updating last touch", () => {
    window.history.replaceState(
      {},
      "",
      "/store?utm_source=google&utm_medium=organic&utm_campaign=prompt&referral_code=partner-7",
    );
    captureAttribution("https://graxia.store/store?utm_source=google&utm_medium=organic&utm_campaign=prompt&referral_code=partner-7");

    window.history.replaceState(
      {},
      "",
      "/revenue-os?utm_source=line&utm_medium=organic&utm_campaign=saas",
    );
    captureAttribution("https://graxia.store/revenue-os?utm_source=line&utm_medium=organic&utm_campaign=saas");

    const attribution = getAttribution();
    expect(attribution.first_touch?.source).toBe("google");
    expect(attribution.last_touch?.source).toBe("line");
    expect(attribution.landing_path).toBe("/store");
    expect(attribution.referral_code).toBe("partner-7");
  });

  it("exposes only non-PII event fields", () => {
    window.history.replaceState({}, "", "/store?utm_source=x&utm_medium=social");
    captureAttribution("https://graxia.store/store?utm_source=x&utm_medium=social");
    const fields = getAttributionEventFields({ content_id: "product-1", email: "bad" });

    expect(fields.source).toBe("x");
    expect(fields.medium).toBe("social");
    expect(fields.first_touch?.source).toBe("x");
    expect(fields.last_touch?.source).toBe("x");
    expect(fields.landing_path).toBe("/store");
    expect(fields.metadata_json).toEqual({ content_id: "product-1" });
    expect(JSON.stringify(fields)).not.toContain("bad@example.com");
  });
});
