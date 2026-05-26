#!/usr/bin/env python3
"""Test the redesigned tag picker modal UI."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # Show browser so we can see it
    page = browser.new_page()
    page.goto('http://localhost:5050', wait_until='domcontentloaded')
    page.wait_for_timeout(2000)  # Wait a couple seconds for JS to load

    # Take initial screenshot
    print("📸 Taking initial screenshot...")
    page.screenshot(path='/tmp/initial.png', full_page=True)

    # Check if there are any email rows
    rows = page.locator('tr[id^="row-"]').all()
    print(f"Found {len(rows)} email rows")

    if len(rows) > 0:
        # Click the tag picker button on the first row
        first_row = rows[0]
        tag_btn = first_row.locator('.btn-pick')
        print("📍 Clicking tag picker button on first row...")
        tag_btn.click()

        # Wait for modal to appear
        page.wait_for_selector('#tagModal.active', timeout=2000)
        print("✓ Modal appeared")

        # Take screenshot of modal
        page.screenshot(path='/tmp/modal_opened.png', full_page=True)
        print("📸 Modal screenshot saved")

        # Test clicking a label to select it
        labels = page.locator('.tag-item-name')
        if labels.count() > 0:
            first_label = labels.nth(0)
            print(f"📝 First label: {first_label.text_content()}")
            first_label.click()

            page.wait_for_timeout(500)
            page.screenshot(path='/tmp/modal_selected.png', full_page=True)
            print("📸 Screenshot after selecting first label")

            # Try clicking the remove button
            remove_btn = page.locator('.tag-item-remove').first
            if remove_btn.is_visible():
                print("🗑️ Clicking remove button...")
                remove_btn.click()
                page.wait_for_timeout(500)
                page.screenshot(path='/tmp/modal_removed.png', full_page=True)
                print("📸 Screenshot after removing label")

        # Confirm selection
        confirm_btn = page.locator('.modal .btn-confirm')
        print("✓ Clicking confirm...")
        confirm_btn.click()
        page.wait_for_timeout(500)
        page.screenshot(path='/tmp/modal_confirmed.png', full_page=True)
        print("✓ Modal closed")
    else:
        print("⚠️ No email rows found - injecting test data...")
        # Inject test data for modal testing
        page.evaluate("""
            EMAILS.push({
                id: 'test1',
                from: 'test@example.com',
                subject: 'Test Email',
                body_snippet: 'This is a test email'
            });
            DECISIONS.push({
                action: ['tag:Important'],
                reasoning: 'Test reasoning'
            });
            state.push({
                status: 'pending',
                action: null,
                mark_read: false,
                delete_later: false
            });

            const tbody = document.getElementById('emailTable');
            tbody.innerHTML += buildRow(0).outerHTML;
        """)

        page.wait_for_timeout(500)
        page.screenshot(path='/tmp/initial.png', full_page=True)

        # Now try to open the tag picker modal
        rows = page.locator('tr[id^="row-"]').all()
        print(f"After injection: Found {len(rows)} email rows")

        if len(rows) > 0:
            first_row = rows[0]
            tag_btn = first_row.locator('.btn-pick')
            print("📍 Clicking tag picker button...")
            tag_btn.click()

            # Wait for modal
            page.wait_for_selector('#tagModal.active', timeout=2000)
            print("✓ Modal appeared")

            # Take screenshot of modal
            page.screenshot(path='/tmp/modal_opened.png', full_page=True)
            print("📸 Modal screenshot saved")

            # Test selecting a label by clicking on it
            labels = page.locator('.tag-item-name')
            if labels.count() > 0:
                first_label = labels.nth(0)
                label_text = first_label.text_content()
                print(f"📝 Clicking first label: {label_text}")
                first_label.click()
                page.wait_for_timeout(300)
                page.screenshot(path='/tmp/modal_label_selected.png', full_page=True)
                print("📸 Screenshot after selecting label")

                # Check if "Chosen" section is now visible
                chosen_section = page.locator('#chosenSection')
                if chosen_section.is_visible():
                    print("✓ Chosen section is now visible")

                # Test clicking remove button on chosen tag
                remove_btn = page.locator('.tag-item-remove').first
                if remove_btn.is_visible():
                    print("🗑️ Clicking remove button...")
                    remove_btn.click()
                    page.wait_for_timeout(300)
                    page.screenshot(path='/tmp/modal_label_removed.png', full_page=True)
                    print("📸 Screenshot after removing label")

                    # Verify chosen section is hidden again
                    if not chosen_section.is_visible():
                        print("✓ Chosen section hidden after removing all tags")

            # Test filter functionality
            filter_input = page.locator('#tagFilter')
            print("🔍 Testing filter...")
            filter_input.fill('eng')
            page.wait_for_timeout(300)
            page.screenshot(path='/tmp/modal_filtered.png', full_page=True)
            print("📸 Screenshot after filtering")

            # Confirm selection (use ID selector to be specific)
            confirm_btn = page.locator('#tagModal .btn-confirm')
            print("✓ Clicking confirm...")
            confirm_btn.click()
            page.wait_for_timeout(500)
            page.screenshot(path='/tmp/modal_confirmed.png', full_page=True)
            print("✓ Modal closed after confirmation")

    browser.close()
    print("✓ Test complete")
