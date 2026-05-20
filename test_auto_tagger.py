#!/usr/bin/env python3
# test_auto_tagger.py — Unit tests for auto-tagging with mock data (no Gmail API required)

"""
Demonstrates the core few-shot learning logic using synthetic emails that mirror
real ones in your examples.json. Run directly to see predictions, then compare them
to expected outputs and tune the training set accordingly.

Example selection is based on content similarity (sender + subject + body overlap),
not just recency — so the model sees the most relevant prior decisions.
"""


import sys; sys.path.insert(0, ".")  # so imports like fetch_emails work

from auto_tagger import (    # noqa: F401,F821
    load_examples, extract_user_labels, pick_labels_from_prompt,
    auto_tag_email, EmailDecision as Decision,
    _example_similarity_score, _select_similar_examples,
)


def run_demo(args=None):
    """Run the demo with mock data — no auth required."""
    print("\n" + "="*70)
    print("  Auto-Tagger Demo (no Gmail API)")
    print("="*70)

    # ----------------------------------------------------------------------
    # Build a training set similar to real examples.json. Each entry has
    # from, subject, body (full text), and the action that was taken.
    # ----------------------------------------------------------------------
    seed_examples: list[dict] = [
        {
            "from": "ngrok team",
            "subject": "Your endpoint is open",
            "body": "Hi there, your ngrok endpoint is now live and ready to accept connections. You can share the URL with your team.",
            "action": ["tag:EngSW/LLM"],
        },
        {
            "from": "Mercado Livre",
            "subject": "Compra está a caminho",
            "body": "Olá! Seu pedido foi enviado e chegará em 3 dias úteis. Acompanhe o rastreamento pelo app.",
            "action": "delete",
        },
        {
            "from": "99Pay",
            "subject": "Seu Pix foi realizado",
            "body": "Pix de R$ 150,00 enviado para João Silva com sucesso. Comprovante disponível no app.",
            "action": "delete",
        },
        {
            "from": "Filipe Newsletter",
            "subject": "Devs ficando \"burros\"",
            "body": "Nesta edição: como o uso excessivo de LLMs está afetando a capacidade de raciocínio dos devs. Artigos e reflexões sobre o futuro da programação.",
            "action": ["tag:InovaçãoTecnológica"],
        },
        {
            "from": "Avenue Security",
            "subject": "Extrato mensal disponível",
            "body": "Seu extrato de investimentos nos EUA está disponível. Acesse o portal para visualizar posições, dividendos e performance.",
            "action": ["tag:Unibanco-Itaú/Investimentos/USA"],
        },
        {
            "from": "Kidslox",
            "subject": "Multiple PIN attempts",
            "body": "We detected multiple incorrect PIN attempts on your child's device. Please review activity and update your security settings.",
            "action": ["tag:Família/Crianças"],
        },
        {
            "from": "Google family",
            "subject": "Family activity report",
            "body": "Weekly family activity report: screen time, app usage, and location history for all family members. Review in the Family Link app.",
            "action": ["tag:Família/Crianças"],
        },
    ] * 7

    # ----------------------------------------------------------------------
    # Simulate a fresh inbox of unread emails to be tagged. Each tuple is:
    #   (realistic_from, realistic_subject, body, expected_tag_or_delete)
    # ----------------------------------------------------------------------
    test_cases: list[tuple[str, str, str, str]] = [
        (
            "ngrok team",
            "A couple more ngrok tips",
            "Here are some advanced ngrok configurations for tunneling WebSocket connections and custom domains. Check out the docs for more.",
            "EngSW/LLM",
        ),
        (
            "Filipe Newsletter",
            "Tokenmaxxing na Amazon / Microsoft:",
            "Análise detalhada sobre o uso massivo de tokens de IA nas big techs. Custos, eficiência e o futuro dos modelos de linguagem corporativos.",
            "InovaçãoTecnológica",
        ),
        (
            "Mercado Livre",
            "Dê sua opinião sobre Suporte Base Refrigeração...",
            "Queremos ouvir você! Avalie sua experiência recente com o produto Suporte Base Refrigeração. Responda nossa pesquisa de satisfação.",
            "delete",
        ),
        (
            "99Pay",
            "Seu Pix foi realizado com sucesso!",
            "Comprovante: Pix de R$ 89,90 enviado para Maria Santos. Data: 20/05/2026. Dúvidas? Acesse o suporte no app.",
            "delete",
        ),
        (
            "Avenue Security",
            "Errata — Nova data: migração da Conta corrente em 18 de maio",
            "Informamos que a data de migração da conta corrente foi alterada para 18 de maio. Pedimos desculpelo pelo transtorno. Para mais detalhes, acesse o portal.",
            "Unibanco-Itaú/Investimentos/USA",
        ),
        (
            "Google family",
            "Review Patricia's activity on their Google Account",
            "Patricia used 4h 32m of screen time this week. Top apps: YouTube (2h), TikTok (1h 30m). Location history shows school and home. Review settings in Family Link.",
            "Família/Crianças",
        ),
    ]

    # ----------------------------------------------------------------------
    # Run predictions and compare them to expected outputs.
    # ----------------------------------------------------------------------
    all_passed = True

    print(f"\n{'='*69}")
    print(f"Running {len(test_cases)} test cases with {len(seed_examples)} examples...")
    print(f"  (similarity-based selection, top-{9} examples per inference)")
    print('='*69)

    for idx, (from_addr, subject, body, expected_label) in enumerate(test_cases, start=1):
        decision = auto_tag_email({
            "from_field": from_addr,
            "subject": subject.strip(),
            "snippet": body[:200],
            "body_snippet": body[:200],
        }, examples=seed_examples, max_examples=9)

        # decision.action is either a string ("delete") or a list (["tag:LABEL"])
        if isinstance(decision.action, list):
            result = decision.action[0] if decision.action else None
        else:
            result = decision.action

        if expected_label == "delete":
            passed = result == "delete"
        else:
            expected = "tag:" + expected_label
            passed = bool(result) and (result == expected or result.lower() == expected.lower())

        all_passed &= passed

        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"\n[{status}] Test {idx:2d} — From:{from_addr!r:<30} Subject:{subject[:55]!r}")
        if passed:
            print(f"         Action  : {decision.action!r}")
        else:
            print(f"         Expected: {expected!r}  Got: {decision.action!r}")
        if decision.reasoning:
            # indent each line of the reason for readability
            for line in decision.reasoning.split("\n"):
                print(f"         Reason  : {line}")

    # ----------------------------------------------------------------------
    # Print aggregate stats for quick sanity checks.
    # ----------------------------------------------------------------------
    total = len(seed_examples) + len(test_cases)
    tagged = sum(
        1 for d in [
            auto_tag_email(
                {"from_field": t[0], "subject": t[1], "snippet": t[2][:200], "body_snippet": t[2][:200]},
                seed_examples,
                max_examples=9,
            )
            for t in test_cases
        ]
        if d.action
    )

    print("\n" + "="*69)
    if all_passed:
        print(f"  ✅ ALL TESTS PASSED ({tagged}/{total} tagged correctly)")
        print("="*69); sys.exit(0)   # noqa: F541,F821,F405

    else:
        print(f"  ⚠ SOME TESTS FAILED — review expected outputs in test_auto_tagger.py"); sys.exit(1)


def main():
    """Entry point for both interactive demo and pytest suite."""
    import argparse; ap = argparse.ArgumentParser(description="Auto-Tagger test harness")   # noqa: F821

    g = ap.add_argument_group("mode", "Choose how to run this script.")
    g.add_argument("--demo","-d", action="store_true", default=True,  help="Run built-in demo (default)")
    g.add_argument("--from-file","-f", metavar="JSON_FILE",          help="Load test cases from a JSON file instead of the builtin set")

    ap.set_defaults(func=run_demo)
    args = ap.parse_args()
    sys.exit(0 if args.func(args) else 1)

if __name__ == "__main__":
    main()
