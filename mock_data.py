#!/usr/bin/env python3
"""Shared mock email data for test_auto_tagger.py and test_dashboard_rendering.py"""

# Real and realistic emails for dashboard rendering and auto-tagging tests
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
        'body_snippet': 'Weekly family activity report: screen time, app usage, and location history for all family members. Review settings and adjust parental controls. Patricia: 4h 32m. Lucas: 3h 15m.'
    },
    {
        'id': 'test7',
        'from': 'LUIZ ROBERTO Nascimento <lroberto2006@gmail.com>',
        'subject': 'Descartes',
        'body_snippet': 'Fonte: O Antagonista https://share.google/fHrXlxuIlY8tgsTWD'
    },
    {
        'id': 'test8',
        'from': 'LUIZ ROBERTO Nascimento <lroberto2006@gmail.com>',
        'subject': 'Foto de Homenagem a Dr Edison',
        'body_snippet': ''
    },
]

MOCK_DECISIONS = [
    {'action': ['tag:EngSW/LLM'], 'reasoning': 'High-confidence match: similar to ngrok team with subject "endpoint". Using cached auto-tag decision from similar infrastructure notifications.'},
    {'action': 'delete', 'reasoning': 'Rule-based similarity scores: Mercado_Livre=8.5. Matches transactional email pattern from e-commerce platform. Not actionable (tracking info).'},
    {'action': 'delete', 'reasoning': 'High-confidence match: similar to 99Pay with subject "Pix". Financial transaction confirmation. Pattern: payment notification → archive/delete.'},
    {'action': ['tag:InovaçãoTecnológica'], 'reasoning': 'Pattern match: Filipe Newsletter sends tech/innovation content. Subject mentions LLM impact. Reasoning: educational content on AI trends.'},
    {'action': ['tag:Unibanco-Itaú/Investimentos/USA'], 'reasoning': 'Rule-based similarity: Avenue domain=5.0, Investment statement=9.5. Financial statement matching investment portfolio tag.'},
    {'action': ['tag:Família/Crianças'], 'reasoning': 'High-confidence match: similar to Google Family Link reports. Family activity monitoring message. Contains child usage data.'},
    {'action': ['tag:UniPalmares'], 'reasoning': 'Educational content about Descartes and philosophy, consistent with previous emails tagged as UniPalmares.'},
    {'action': ['tag:Fotos'], 'reasoning': 'Photo/image email indicated by "Foto" in subject. Tagged with Fotos for organization.'},
]

# Training examples for auto-tagger (seed data for few-shot learning)
TRAINING_EXAMPLES = [
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
        "from": "Google family",
        "subject": "Family activity report",
        "body": "Weekly family activity report: screen time, app usage, and location history for all family members. Review in the Family Link app.",
        "action": ["tag:Família/Crianças"],
    },
    {
        "from": "Kidslox",
        "subject": "Multiple PIN attempts",
        "body": "We detected multiple incorrect PIN attempts on your child's device. Please review activity and update your security settings.",
        "action": ["tag:Família/Crianças"],
    },
    # Educational and university-related content (with substantial text content)
    {
        "from": "LUIZ ROBERTO Nascimento <lroberto2006@gmail.com>",
        "subject": "Aristóteles e Kant",
        "body": "Referência: UniPalmares. Análise histórica sobre duas escolas filosóficas clássicas. Discusses philosophical concepts and theoretical frameworks.",
        "action": ["tag:UniPalmares"],
    },
    {
        "from": "O Antagonista",
        "subject": "Pensadores clássicos",
        "body": "Artigo sobre a filosofia de Descartes e seu impacto. Fonte: estudos universitários. Deep analysis of classical thought and rationalism.",
        "action": ["tag:UniPalmares"],
    },
    {
        "from": "LUIZ ROBERTO Nascimento <lroberto2006@gmail.com>",
        "subject": "Filosofia e pensamento crítico",
        "body": "Resumo das aulas sobre Descartes, Spinoza e epistemologia. Conteúdo acadêmico relacionado a UniPalmares.",
        "action": ["tag:UniPalmares"],
    },
    # Photo/image emails - tag with Fotos
    {
        "from": "LUIZ ROBERTO Nascimento <lroberto2006@gmail.com>",
        "subject": "Foto de homenagem",
        "body": "Compartilhando uma foto de homenagem",
        "action": ["tag:Fotos"],
    },
    {
        "from": "LUIZ ROBERTO Nascimento <lroberto2006@gmail.com>",
        "subject": "Foto de Homenagem",
        "body": "",
        "action": ["tag:Fotos"],
    },
    {
        "from": "LUIZ ROBERTO Nascimento <lroberto2006@gmail.com>",
        "subject": "Foto de família",
        "body": "Compartilhando foto",
        "action": ["tag:Fotos"],
    },
    {
        "from": "LUIZ ROBERTO Nascimento <lroberto2006@gmail.com>",
        "subject": "Imagem do projeto",
        "body": "Foto",
        "action": ["tag:Fotos"],
    },
    {
        "from": "LUIZ ROBERTO Nascimento <lroberto2006@gmail.com>",
        "subject": "Foto de Homenagem a Dr Edison",
        "body": "",
        "action": ["tag:Fotos"],
    },
    # Marketing and feedback emails (delete)
    {
        "from": "Mercado Livre",
        "subject": "Avalie sua compra",
        "body": "Queremos ouvir sua opinião sobre o produto. Responda nossa pesquisa de satisfação.",
        "action": "delete",
    },
    {
        "from": "Mercado Livre",
        "subject": "Feedback do cliente",
        "body": "Sua opinião é importante para melhorar nossos serviços. Clique aqui para avaliar.",
        "action": "delete",
    },
]
