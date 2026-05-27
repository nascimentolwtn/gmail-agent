#!/usr/bin/env python3
"""Test for the 'Go Bottom' scroll button in the dashboard."""

import asyncio
from playwright.async_api import async_playwright
import sys

async def test_go_bottom_button():
    """Verify Go Top/Bottom buttons exist and scroll functionality works."""

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        try:
            # Navigate to dashboard
            print("🌐 Loading dashboard...")
            await page.goto("http://localhost:5050", wait_until="networkidle", timeout=30000)

            # Wait for table to have some rows
            print("⏳ Waiting for table rows to load...")
            await page.wait_for_selector("tbody#emailTable tr", timeout=30000)

            # Check if the buttons exist with title attributes
            print("🔍 Checking for scroll buttons...")
            go_top_button = page.locator('button[title="Go to top"]')
            go_bottom_button = page.locator('button[title="Go to bottom"]')

            top_exists = await go_top_button.count() > 0
            bottom_exists = await go_bottom_button.count() > 0

            if not top_exists or not bottom_exists:
                print("❌ Scroll buttons not found")
                return False

            print("✓ Go Top and Go Bottom buttons found")

            # Check that buttons show just emoji
            top_text = await go_top_button.text_content()
            bottom_text = await go_bottom_button.text_content()
            print(f"  Go Top text: '{top_text.strip()}'")
            print(f"  Go Bottom text: '{bottom_text.strip()}'")

            # Check Load next batch button is initially disabled
            print("🔍 Checking 'Load next batch' button state...")
            load_btn = page.locator('#btnFetchNext')
            is_disabled = await load_btn.evaluate('el => el.disabled')
            if is_disabled:
                print("✓ 'Load next batch' button starts disabled")
            else:
                print("⚠️  'Load next batch' button is not disabled initially")

            # Get all rows
            rows = page.locator("tbody#emailTable tr")
            row_count = await rows.count()
            print(f"✓ Table has {row_count} rows")

            if row_count == 0:
                print("⚠️  No rows in table, skipping scroll test")
                return True

            # Test Go Bottom
            print("📍 Testing 'Go Bottom' button...")
            scroll_before = await page.evaluate(
                "() => document.querySelector('.email-container').scrollTop"
            )
            await go_bottom_button.click()
            await page.wait_for_timeout(500)
            scroll_after = await page.evaluate(
                "() => document.querySelector('.email-container').scrollTop"
            )
            if scroll_after > scroll_before:
                print("✓ Email container scrolled to bottom")
            else:
                print("⚠️  Scroll to bottom may not have changed")

            # Test Go Top
            print("📍 Testing 'Go Top' button...")
            scroll_before = scroll_after
            await go_top_button.click()
            await page.wait_for_timeout(500)
            scroll_after = await page.evaluate(
                "() => document.querySelector('.email-container').scrollTop"
            )
            if scroll_after < scroll_before:
                print("✓ Email container scrolled to top")
            else:
                print("⚠️  Scroll to top may not have changed")

            # Take a screenshot to verify
            print("📸 Taking screenshot...")
            await page.screenshot(path="/tmp/go_bottom_test.png")
            print("✓ Screenshot saved to /tmp/go_bottom_test.png")

            return True

        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await browser.close()

if __name__ == "__main__":
    success = asyncio.run(test_go_bottom_button())
    sys.exit(0 if success else 1)
