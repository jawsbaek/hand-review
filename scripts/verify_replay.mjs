// Run after generating an HTML report. Only local files are opened; all requests
// except the report itself are rejected. Screenshots remain in an ignored folder.
// PLAYWRIGHT_MODULE can point to an already installed Playwright package.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const artifact = path.resolve(process.argv[2] || "reports/demo.html");
const screenshots = path.resolve(process.argv[3] || ".impeccable/review");
await mkdir(screenshots, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  // macOS's workspace sandbox permits one process but not Chromium's Mach IPC.
  args:
    process.platform === "darwin"
      ? ["--single-process", "--in-process-gpu", "--disable-gpu"]
      : [],
});
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "reduce",
  });
  const errors = [],
    externalRequests = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) => {
    if (route.request().url() === pathToFileURL(artifact).href)
      return route.continue();
    externalRequests.push(route.request().url());
    return route.abort();
  });
  await page.goto(pathToFileURL(artifact).href);
  const data = await page
    .locator("#report-data")
    .textContent()
    .then(JSON.parse);
  assert.ok(data.hands.length > 0);
  assert.equal(
    await page.locator("#seats .seat").count(),
    data.hands.find((h) =>
      h.decisions.some(
        (d) => d.stage !== "Preflop" && d.review.grade === "best",
      ),
    )?.frames[0].players.length ?? data.hands[0].frames[0].players.length,
  );
  assert.equal(await page.locator("#board .placeholder").count(), 5);
  assert.equal(
    await page.locator("#seats .seat:not(.hero) .card:not(.back)").count(),
    0,
  );

  for (const grade of ["blunder", "best", "review", "unscored"]) {
    await page
      .getByRole("button", {
        name: new RegExp(
          "^" +
            {
              blunder: "블런더",
              best: "베스트",
              review: "검토",
              unscored: "미평가",
            }[grade] +
            " ",
        ),
      })
      .click();
    assert.equal(
      await page.evaluate(() => document.activeElement.dataset.filter),
      grade,
    );
    assert.equal(
      await page.locator(".hand-row").count(),
      data.grades[grade] || 0,
    );
    if (data.grades[grade]) {
      await page.locator(".hand-row").first().focus();
      await page.keyboard.press("Enter");
      assert.ok(
        await page.evaluate(() =>
          document.activeElement.classList.contains("hand-row"),
        ),
      );
      assert.equal(await page.locator("#decision .badge." + grade).count(), 1);
    }
  }
  await page.locator("#search").fill("__no_such_hand__");
  assert.equal(await page.locator(".hand-row").count(), 0);
  assert.ok(
    await page
      .locator("#hand-list")
      .textContent()
      .then((s) => s.includes("없습니다")),
  );
  await page.locator("#search").fill("");
  await page.getByRole("button", { name: /^전체 / }).click();
  await page.locator(".hand-row").first().click();
  const firstHand = data.hands[0];
  await page.locator("#next").click();
  assert.equal(Number(await page.locator("#scrubber").inputValue()), 1);
  await page.locator("#previous").click();
  assert.equal(Number(await page.locator("#scrubber").inputValue()), 0);
  await page.locator("#unit").selectOption("chips");
  if (firstHand.frames[0].pot !== null)
    assert.ok((await page.locator("#pot").textContent()).includes("칩"));
  await page.locator("#unit").selectOption("bb");

  // Practice must stop at the first unanswered decision, even when scrubbing
  // straight to the end. Actual actions/grades remain hidden until a choice.
  await page.locator("#mode").selectOption("practice");
  const firstDecision = firstHand.decisions[0];
  if (firstDecision) {
    await page.locator("#scrubber").evaluate((n) => {
      n.value = n.max;
      n.dispatchEvent(new Event("input"));
    });
    assert.equal(
      Number(await page.locator("#scrubber").inputValue()),
      firstDecision.frame,
    );
    assert.equal(await page.locator("#decision .badge").count(), 0);
    assert.equal(
      await page.locator(".practice-buttons button").count(),
      firstDecision.spot.to_call > 0 && firstDecision.spot.can_raise ? 3 : 2,
    );
    await page.locator(".practice-buttons button").first().focus();
    await page.keyboard.press("Enter");
    assert.equal(
      await page.evaluate(() => document.activeElement.id),
      "replay-action",
    );
    assert.equal(await page.locator("#decision .badge").count(), 1);
    assert.ok(
      (await page.locator("#decision").textContent()).includes("내 선택:"),
    );
    await page.getByRole("button", { name: "기록된 액션 재생" }).click();
    assert.equal(await page.evaluate(() => document.activeElement.id), "next");
    assert.equal(
      Number(await page.locator("#scrubber").inputValue()),
      firstDecision.action_frame,
    );
    await page.locator("#restart").click();
    await page.locator("#speed").selectOption("4");
    await page.locator("#play").click();
    await page.waitForFunction(
      (target) => Number(document.getElementById("scrubber").value) === target,
      firstDecision.frame,
    );
    assert.equal(
      await page.locator("#play").getAttribute("aria-label"),
      "재생",
    );
    assert.equal(await page.locator("#decision .badge").count(), 0);
  }
  await page.locator("#mode").selectOption("review");
  await page.locator("#restart").click();
  await page.locator("#play").click();
  if (data.hands.length > 1) await page.locator(".hand-row").nth(1).click();
  else await page.locator("#restart").click();
  await page.waitForTimeout(500);
  assert.equal(Number(await page.locator("#scrubber").inputValue()), 0);

  // Inspect a meaningful postflop candidate at both sizes in one capture round.
  await page.getByRole("button", { name: /^베스트 / }).click();
  const example = data.hands.find((h) =>
    h.decisions.some((d) => d.stage !== "Preflop" && d.review.grade === "best"),
  );
  if (example) {
    const scene = example.decisions.find(
      (d) => d.stage !== "Preflop" && d.review.grade === "best",
    );
    await page
      .locator(".hand-row")
      .filter({
        hasText:
          "#" + String(example.number).padStart(2, "0") + " · " + scene.stage,
      })
      .first()
      .click();
    assert.equal(
      await page.locator("#board .card:not(.placeholder)").count(),
      scene.stage === "Flop" ? 3 : scene.stage === "Turn" ? 4 : 5,
    );
    assert.equal(
      await page.locator("#seats .seat:not(.hero) .card:not(.back)").count(),
      0,
    );
    await page.locator("#hide-result").uncheck();
    assert.ok(
      (await page.locator("#result").textContent()).includes("기록 Net"),
    );
    await page.locator("#hide-result").check();
  }
  const dimensions = [];
  for (const [name, width, height] of [
    ["desktop", 1440, 1000],
    ["mobile", 390, 844],
  ]) {
    await page.setViewportSize({ width, height });
    await page.evaluate(() => window.scrollTo(0, 0));
    const metrics = await page.evaluate(() => ({
      width: innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    assert.ok(
      metrics.scrollWidth <= width,
      `${name}: horizontal overflow ${metrics.scrollWidth}`,
    );
    dimensions.push({ name, ...metrics });
    await page.screenshot({
      path: path.join(screenshots, name + ".png"),
      fullPage: true,
    });
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(externalRequests, []);
  console.log(
    JSON.stringify(
      {
        hands: data.hands.length,
        grades: data.grades,
        checks: "passed",
        dimensions,
        screenshots,
      },
      null,
      2,
    ),
  );
} finally {
  await browser.close();
}
