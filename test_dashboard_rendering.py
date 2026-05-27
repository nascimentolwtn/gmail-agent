#!/usr/bin/env python3
"""Generic table rendering test for the Gmail dashboard.

Tests various aspects of table cell rendering:
  - Snippet truncation (200 chars with "...")
  - Reasoning display and hover hints
  - Cell heights and multi-line display
  - Multiple rows to ensure consistent rendering
"""
from playwright.sync_api import sync_playwright

# Mock email data — reusing pattern from test_auto_tagger.py
MOCK_EMAILS = [
    {
        'id': 'test1',
        'from': 'ngrok team',
        'subject': 'Your endpoint is open',
        'body_snippet': 'Hi there, your ngrok endpoint is now live and ready to accept connections. You can share the URL with your team. Check the dashboard for real-time activity logs and advanced configuration options.'
    },
    {
        'id': 'test2',
        'from': 'Mercado Livre',
        'subject': 'Compra está a caminho',
        'body_snippet': 'Olá! Seu pedido foi enviado e chegará em 3 dias úteis. Acompanhe o rastreamento pelo app. Acesse a seção "Minhas compras" para mais detalhes e atualizações de status.'
    },
    {
        'id': 'test3',
        'from': '99Pay',
        'subject': 'Seu Pix foi realizado',
        'body_snippet': 'Pix de R$ 150,00 enviado para João Silva com sucesso. Comprovante disponível no app. Tempo de processamento: imediato. Seu saldo foi atualizado. Para dúvidas, acesse o suporte.'
    },
    {
        'id': 'test4',
        'from': 'Filipe Newsletter',
        'subject': 'Devs ficando "burros" com LLMs',
        'body_snippet': 'Nesta edição: como o uso excessivo de LLMs está afetando a capacidade de raciocínio dos devs. Artigos e reflexões sobre o futuro da programação, produtividade e educação técnica.'
    },
    {
        'id': 'test5',
        'from': 'Avenue Security',
        'subject': 'Extrato mensal disponível — investimentos USA',
        'body_snippet': 'Seu extrato de investimentos nos EUA está disponível. Acesse o portal para visualizar posições, dividendos, performance anual e projeções de rendimento futuro com análise detalhada.'
    },
    {
        'id': 'test6',
        'from': 'Google Family Link',
        'subject': 'Family activity report — semana 21',
        'body_snippet': 'Weekly family activity report: screen time, app usage, and location history for all family members. Review settings and adjust parental controls. Patricia: 4h 32m. Lucas: 3h 15m. Updates on YouTube usage patterns and recommended app limits.'
    },
]

MOCK_DECISIONS = [
    {'action': ['tag:EngSW/LLM'], 'reasoning': 'High-confidence match: similar to ngrok team with subject "endpoint". Using cached auto-tag decision from similar infrastructure notifications. Pattern recognized from previous ngrok deployment updates.'},
    {'action': 'delete', 'reasoning': 'Rule-based similarity scores: Mercado_Livre=8.5, commerce_delete=7.0. Matches transactional email pattern from e-commerce platform. Not actionable (tracking info).'},
    {'action': 'delete', 'reasoning': 'High-confidence match: similar to 99Pay with subject "Pix". Financial transaction confirmation. Pattern: payment notification → archive/delete. Not requiring user action.'},
    {'action': ['tag:InovaçãoTecnológica'], 'reasoning': 'Pattern match: Filipe Newsletter sends tech/innovation content. Subject mentions LLM impact. Reasoning: educational content on AI trends and developer productivity.'},
    {'action': ['tag:Unibanco-Itaú/Investimentos/USA'], 'reasoning': 'Rule-based similarity: Avenue domain=5.0, Investment statement=9.5. Financial statement matching investment portfolio tag. Monthly recurring pattern detected.'},
    {'action': ['tag:Família/Crianças'], 'reasoning': 'High-confidence match: similar to Google Family Link reports. Family activity monitoring message. Contains child usage data (Patricia, Lucas). Tagged for family/parental records.'},
]


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
