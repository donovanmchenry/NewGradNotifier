#!/usr/bin/env python3
"""Probe the Story viewer with a real browser and save diagnostic artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright


DEFAULT_URL = "https://insta-stories-viewer.com/zero2sudo/"


async def _collect_diagnostics(page: Page) -> dict[str, Any]:
    return await page.evaluate(
        r"""
        () => {
          const absolute = (value) => {
            try { return new URL(value, document.baseURI).href; }
            catch { return value || ""; }
          };
          const unique = (values) => [...new Set(values.filter(Boolean))];
          const metadataItems = [...document.querySelectorAll(
            '[data-type="stories"][data-id], [data-type="story"][data-id]'
          )];
          const proxyImages = [...document.querySelectorAll('img')].filter((image) => {
            const src = image.currentSrc || image.src || '';
            return /\/img(?:2)?\.php\?url=/i.test(src);
          });
          const proxyVideos = [...document.querySelectorAll('video')];
          const storyTab = [...document.querySelectorAll('a, button, [role="tab"]')]
            .find((element) => element.textContent.trim().toLowerCase() === 'stories');

          const describe = (element) => {
            const parents = [];
            let current = element;
            for (let depth = 0; current && depth < 4; depth += 1, current = current.parentElement) {
              parents.push({
                tag: current.tagName,
                id: current.id || '',
                className: typeof current.className === 'string' ? current.className : '',
                dataType: current.dataset?.type || '',
                dataId: current.dataset?.id || '',
              });
            }
            return parents;
          };

          return {
            title: document.title,
            finalUrl: location.href,
            bodyTextSample: (document.body?.innerText || '').slice(0, 3000),
            metadataCount: metadataItems.length,
            metadata: metadataItems.map((item) => ({
              id: item.dataset.id || '',
              content: item.dataset.content || '',
              type: item.dataset.type || '',
            })),
            proxyImageCount: proxyImages.length,
            proxyImageUrls: unique(proxyImages.map((image) => absolute(image.currentSrc || image.src))),
            proxyVideoCount: proxyVideos.length,
            videoUrls: unique(proxyVideos.flatMap((video) => [
              video.currentSrc,
              video.src,
              ...[...video.querySelectorAll('source')].map((source) => source.src),
            ]).map(absolute)),
            storyTabFound: Boolean(storyTab),
            storyTabContext: storyTab ? describe(storyTab) : [],
            imageContexts: proxyImages.slice(0, 8).map(describe),
          };
        }
        """
    )


async def _dismiss_common_overlays(page: Page) -> None:
    labels = ("Accept", "Accept all", "Allow all", "I agree", "Got it")
    for label in labels:
        button = page.get_by_role("button", name=label, exact=True)
        try:
            if await button.first.is_visible(timeout=300):
                await button.first.click(timeout=1_000)
                break
        except Exception:
            continue


async def run_probe(url: str, output_dir: Path, wait_seconds: float) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context: BrowserContext = await browser.new_context(
            viewport={"width": 1440, "height": 1200},
            locale="en-US",
            timezone_id="America/New_York",
            color_scheme="light",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await context.new_page()
        response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await _dismiss_common_overlays(page)
        await page.wait_for_timeout(int(wait_seconds * 1000))

        diagnostics = await _collect_diagnostics(page)
        diagnostics.update(
            {
                "requestedUrl": url,
                "httpStatus": response.status if response else None,
                "visibleStoryCount": max(
                    diagnostics["metadataCount"],
                    max(0, diagnostics["proxyImageCount"] - 1),
                ),
            }
        )
        await page.screenshot(path=output_dir / "page.png", full_page=True)
        (output_dir / "page.html").write_text(await page.content(), encoding="utf-8")
        await browser.close()

    result_path = output_dir / "result.json"
    result_path.write_text(json.dumps(diagnostics, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "summary.md").write_text(
        "\n".join(
            [
                "## zero2sudo browser probe",
                "",
                f"- HTTP status: `{diagnostics['httpStatus']}`",
                f"- Metadata Story elements: `{diagnostics['metadataCount']}`",
                f"- Viewer-proxied images: `{diagnostics['proxyImageCount']}`",
                f"- Video elements: `{diagnostics['proxyVideoCount']}`",
                f"- Estimated visible Stories: `{diagnostics['visibleStoryCount']}`",
                f"- Final URL: `{diagnostics['finalUrl']}`",
                "",
                "Download the `zero2sudo-browser-probe` artifact for the screenshot, HTML, and JSON.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return diagnostics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/story-probe"))
    parser.add_argument("--wait-seconds", type=float, default=8.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    diagnostics = asyncio.run(run_probe(args.url, args.output_dir, args.wait_seconds))
    print("STORY_PROBE_RESULT=" + json.dumps(diagnostics, separators=(",", ":")))


if __name__ == "__main__":
    main()
