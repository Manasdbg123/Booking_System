import { test, expect, Page } from "@playwright/test";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function pickShow(): Promise<{ showId: string; eventId: string }> {
  const events = await (await fetch(`${API}/api/events`)).json();
  // A non-hot show, so the booking flow isn't gated behind the waiting room.
  const event = events.find((e: any) => !e.is_hot) ?? events[0];
  const detail = await (await fetch(`${API}/api/events/${event.id}`)).json();
  return { showId: detail.shows[0].id, eventId: event.id };
}

async function registerViaUi(page: Page) {
  await page.goto("/login");
  await page.getByText("New here? Create an account").click();
  await page.locator("input[type=email]").fill(`e2e_${Date.now()}_${Math.random().toString(36).slice(2, 7)}@test.dev`);
  await page.locator("input[type=password]").fill("password123");
  await page.locator("button[type=submit]").click();
  await page.waitForURL("/");
}

/**
 * Seats are rendered inside a pan/zoom SVG whose own bounding box extends
 * well outside the visible area, so "is this seat clickable" has to be
 * judged against the clipping frame, not the SVG.
 */
async function clickVisibleSeats(page: Page, count: number, skip = 0): Promise<number> {
  // Candidate ids are gathered in a single evaluate, then clicked by id.
  // Indexing with nth() across awaits is unsafe here: a live seat update or
  // a cleared selection re-renders the map and detaches the element the
  // index pointed at.
  const ids: string[] = await page.evaluate(
    ({ skip, count }) => {
      const frame = document.querySelector("[data-seatmap-frame]");
      if (!frame) return [];
      const f = frame.getBoundingClientRect();
      const picked: string[] = [];
      let skipped = 0;
      for (const cell of Array.from(document.querySelectorAll('[role="gridcell"][aria-disabled="false"]'))) {
        const b = cell.getBoundingClientRect();
        const inside =
          b.left > f.left + 16 && b.top > f.top + 16 && b.right < f.right - 16 && b.bottom < f.bottom - 16;
        if (!inside) continue;
        if (skipped < skip) {
          skipped++;
          continue;
        }
        picked.push(cell.id);
        if (picked.length >= count) break;
      }
      return picked;
    },
    { skip, count }
  );

  let clicked = 0;
  for (const id of ids) {
    // attribute selector, not #id — the ids embed UUIDs that can start with a digit
    await page.locator(`[id="${id}"]`).click();
    clicked++;
  }
  return clicked;
}

/**
 * Selects seats and holds them, retrying on a seat conflict.
 *
 * All the specs run against one shared seeded database and naturally reach
 * for the same first-visible seats, so a later run can legitimately lose
 * the race for them. A 409 here is the app behaving correctly, not a bug —
 * so the test recovers exactly the way the UI tells a real user to: pick
 * different seats and try again.
 */
async function selectAndHold(page: Page, count: number): Promise<void> {
  const conflict = page.getByText(/were just taken/i);

  for (let attempt = 0; attempt < 4; attempt++) {
    const clicked = await clickVisibleSeats(page, count, attempt * count);
    expect(clicked, "ran out of selectable seats in view").toBe(count);

    await holdButton(page).click();

    const outcome = await Promise.race([
      checkoutButton(page)
        .waitFor({ state: "visible", timeout: 12_000 })
        .then(() => "held" as const)
        .catch(() => "timeout" as const),
      conflict
        .waitFor({ state: "visible", timeout: 12_000 })
        .then(() => "conflict" as const)
        .catch(() => "timeout" as const),
    ]);

    if (outcome === "held") return;
    if (outcome === "conflict") {
      // the page refetches the map on conflict; let it re-render before retrying
      await page.waitForTimeout(800);
      continue; // selection was cleared for us
    }
    throw new Error("hold neither succeeded nor reported a conflict");
  }
  throw new Error("could not acquire seats after 4 attempts");
}

/**
 * The hold/checkout actions render twice — once in the sticky summary card
 * and once in the mobile bottom bar — with the irrelevant one hidden by a
 * CSS breakpoint rather than unmounted. Always drive the visible one.
 */
function holdButton(page: Page) {
  return page.getByRole("button", { name: /Hold selected seats|Hold seats/i }).filter({ visible: true }).first();
}

function checkoutButton(page: Page) {
  return page.getByRole("button", { name: /Proceed to checkout|Checkout/i }).filter({ visible: true }).first();
}

test("browse page lists events with prices and availability", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Shows worth/i })).toBeVisible();
  await expect(page.getByText("What's on")).toBeVisible();

  // Event cards carry a "from" price and a seats-left count. Scoped to
  // visible nodes because the featured hero card is display:none below lg
  // and would otherwise be the first match on mobile.
  await expect(page.locator("text=/from/i").filter({ visible: true }).first()).toBeVisible();
  await expect(page.locator("text=/seats left/i").first()).toBeVisible();
});

test("seat map renders a stage, a price legend and selectable seats", async ({ page }) => {
  const { showId } = await pickShow();
  await page.goto(`/shows/${showId}`);

  await expect(page.locator("text=STAGE")).toBeVisible();
  await expect(page.getByText("Platinum", { exact: false }).first()).toBeVisible();
  await expect(page.locator('[role="gridcell"]').first()).toBeVisible();
  await expect(page.getByText(/seats available/)).toBeVisible();
});

test("selecting seats updates the summary total", async ({ page }) => {
  const { showId } = await pickShow();
  await page.goto(`/shows/${showId}`);
  await page.waitForSelector('[role="gridcell"]');

  await expect(page.getByText("No seats picked yet")).toBeVisible();

  const clicked = await clickVisibleSeats(page, 2);
  expect(clicked).toBe(2);

  await expect(page.locator('[role="gridcell"][aria-selected="true"]')).toHaveCount(2);
  // total is no longer zero
  await expect(page.getByText("No seats picked yet")).toBeHidden();
});

test("seats are reachable and selectable by keyboard", async ({ page }) => {
  const { showId } = await pickShow();
  await page.goto(`/shows/${showId}`);
  await page.waitForSelector('[role="gridcell"]');

  await page.locator('[role="gridcell"]').first().focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");

  await expect(page.locator('[role="gridcell"][aria-selected="true"]')).toHaveCount(1);
});

test("full flow: hold seats, pay, and land on a confirmed ticket", async ({ page }) => {
  const { showId } = await pickShow();
  await registerViaUi(page);

  await page.goto(`/shows/${showId}`);
  await page.waitForSelector('[role="gridcell"]');
  await selectAndHold(page, 2);

  await checkoutButton(page).click();
  await page.waitForURL(/\/checkout\//);
  await expect(page.getByRole("heading", { name: "Checkout" })).toBeVisible();

  // force a deterministic success from the mock payment provider
  await page.getByRole("button", { name: "success", exact: true }).click();
  await page.getByRole("button", { name: /^Pay /i }).click();

  // the webhook arrives asynchronously; the page polls until confirmed
  await expect(page.getByText("Payment successful!")).toBeVisible({ timeout: 30_000 });

  await page.getByRole("button", { name: /View your ticket/i }).click();
  await page.waitForURL(/\/tickets\//);
  await expect(page.getByText("SeatRush E-Ticket")).toBeVisible();
});

test("my bookings lists the confirmed booking", async ({ page }) => {
  const { showId } = await pickShow();
  await registerViaUi(page);

  await page.goto(`/shows/${showId}`);
  await page.waitForSelector('[role="gridcell"]');
  await selectAndHold(page, 1);

  await page.goto("/my-bookings");
  await expect(page.getByRole("heading", { name: "My bookings" })).toBeVisible();
  await expect(page.getByText("HELD").first()).toBeVisible();
});
