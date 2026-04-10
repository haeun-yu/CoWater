import test from "node:test";
import assert from "node:assert/strict";

import { parseWsMessage } from "./wsMessage";

test("parseWsMessage accepts valid position_update payloads", () => {
  const message = parseWsMessage(
    JSON.stringify({
      type: "position_update",
      platform_id: "vessel-1",
      platform_type: "vessel",
      timestamp: "2026-04-10T12:00:00Z",
      lat: 37.1,
      lon: 126.9,
      sog: 10.5,
      cog: 182.2,
      heading: 181.0,
      nav_status: "underway_engine",
    }),
  );

  assert.ok(message);
  assert.equal(message?.type, "position_update");
});

test("parseWsMessage rejects malformed alert payloads", () => {
  const message = parseWsMessage(
    JSON.stringify({
      type: "alert_created",
      alert_id: "a-1",
      message: "missing required fields",
    }),
  );

  assert.equal(message, null);
});
