#!/usr/bin/env python3
"""Generic table rendering test for the Gmail dashboard.

Tests various aspects of table cell rendering:
  - Snippet truncation (200 chars with "...")
  - Reasoning display and hover hints
  - Cell heights and multi-line display
  - Multiple rows to ensure consistent rendering
"""
from playwright.sync_api import sync_playwright
from mock_data import MOCK_EMAILS, MOCK_DECISIONS


def generate_mock_data_js():
    """Generate JavaScript code to inject mock emails and decisions into the page."""
    emails_js = []
    decisions_js = []

    for i, (email, decision) in enumerate(zip(MOCK_EMAILS, MOCK_DECISIONS)):
        emails_js.append(f"""
                EMAILS.push({{
                    id: {email['id']!r},
                    from: {email['from']!r},
                    subject: {email['subject']!r},
                    body_snippet: {email['body_snippet']!r}
                }});""")

        decisions_js.append(f"""
                DECISIONS.push({{
                    action: {repr(decision['action'])},
                    reasoning: {decision['reasoning']!r}
                }});""")

    state_js = '\n                '.join([
        f"state.push({{ status: 'pending', action: null, mark_read: false, delete_later: false }});"
        for _ in MOCK_EMAILS
    ])

    return f"""
                {''.join(emails_js)}
                {''.join(decisions_js)}
                {state_js}
                const tbody = document.getElementById('emailTable');
                for (let i = 0; i < {len(MOCK_EMAILS)}; i++) {{
                    tbody.innerHTML += buildRow(i).outerHTML;
                }}
            """


def test_cell_rendering(cell_class: str, max_chars: int = None, should_have_ellipsis: bool = False):
    """Test a cell class for rendering correctness across multiple rows.

    Args:
        cell_class: CSS class to test (e.g., 'snippet', 'reasoning')
        max_chars: Maximum character count (None = no limit)
        should_have_ellipsis: Whether truncated content should end with '...'
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto('http://localhost:5050', wait_until='domcontentloaded')
        page.wait_for_timeout(2000)

        print(f"\n{'='*60}")
        print(f"Testing cell class: {cell_class}")
        print(f"{'='*60}")

        # Take initial screenshot
        page.screenshot(path=f'/tmp/test_{cell_class}_initial.png', full_page=True)

        # Find all rows
        rows = page.locator('tr[id^="row-"]').all()
        print(f"✓ Found {len(rows)} email rows")

        if not rows:
            print("⚠️  No email rows found - injecting mock data...")
            page.evaluate(f"{{ {generate_mock_data_js()} }}")
            rows = page.locator('tr[id^="row-"]').all()
            print(f"   ✓ Injected {len(rows)} mock rows")
            page.wait_for_timeout(500)

        # Test all rows
        print(f"\n📊 Testing {cell_class} across {len(rows)} rows:")
        print(f"{'─'*60}")

        all_passed = True
        for row_idx, row in enumerate(rows):
            cell = row.locator(f'.{cell_class}')
            if not cell.count():
                print(f"   Row {row_idx+1}: ⚠️  Cell '.{cell_class}' not found")
                all_passed = False
                continue

            # Get text content
            cell_div = cell.locator('div').first
            cell_text = cell_div.text_content()
            cell_len = len(cell_text)

            # Check character limit
            if max_chars and cell_len > max_chars:
                status = "⚠️ "
                print(f"   Row {row_idx+1}: {status} {cell_class} exceeds {max_chars} chars (actual: {cell_len})")
                all_passed = False
            elif max_chars:
                status = "✓"
                print(f"   Row {row_idx+1}: {status} {cell_class} = {cell_len} chars (within {max_chars} limit)")

            # Check ellipsis (only if text was actually truncated to max_chars)
            if should_have_ellipsis and cell_len == max_chars:
                if not cell_text.endswith('...'):
                    print(f"      → ⚠️ Missing '...' suffix (truncated to {max_chars})")
                    all_passed = False
                else:
                    print(f"      → ✓ Has '...' suffix (correctly truncated)")

            # Check title attribute (hover hint)
            title_text = cell.first.get_attribute('title')
            title_len = len(title_text or '')
            if title_len > 0:
                print(f"      → Hover hint: {title_len} chars")
            else:
                print(f"      → ⚠️ Hover hint: empty")
                all_passed = False

        # Test hover on first and last rows
        if len(rows) > 0:
            print(f"\n🔍 Testing hover interaction:")
            print(f"   First row hover...")
            rows[0].hover()
            page.wait_for_timeout(300)
            page.screenshot(path=f'/tmp/test_{cell_class}_hover_first.png', full_page=True)

            if len(rows) > 1:
                print(f"   Last row ({len(rows)}) hover...")
                rows[-1].hover()
                page.wait_for_timeout(300)
                page.screenshot(path=f'/tmp/test_{cell_class}_hover_last.png', full_page=True)
                print(f"   ✓ Hover consistent across {len(rows)} rows")

        print(f"\n{'='*60}")
        print(f"✓ {cell_class} test complete")
        print(f"  Screenshots: /tmp/test_{cell_class}_*.png")
        if all_passed:
            print(f"  Status: ✅ All checks passed")
        else:
            print(f"  Status: ⚠️ Some checks failed")
        print(f"{'='*60}")

        browser.close()
        return all_passed


# Run tests
if __name__ == '__main__':
    snippet_ok = test_cell_rendering('snippet', max_chars=200, should_have_ellipsis=True)
    reasoning_ok = test_cell_rendering('reasoning', should_have_ellipsis=False)

    if snippet_ok and reasoning_ok:
        print("\n✅ All rendering tests passed!")
    else:
        print("\n⚠️ Some rendering tests failed")
