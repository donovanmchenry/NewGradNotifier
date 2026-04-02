from newgrad_notifier.config.company_loader import load_company_list, load_default_ats_boards


def test_default_company_list_includes_expanded_high_value_targets():
    companies = load_company_list()
    names = {company["name"] for company in companies}

    assert len(companies) >= 290
    assert {
        "Perplexity",
        "Character.AI",
        "Groq",
        "Together AI",
        "Wiz",
        "Airtable",
        "Linear",
        "Render",
        "Mercury",
        "Snyk",
        "LaunchDarkly",
    } <= names


def test_default_ats_boards_include_new_high_confidence_seed():
    boards = load_default_ats_boards()
    groq_board = next(board for board in boards if board["company_name"] == "Groq")

    assert groq_board["platform"] == "greenhouse"
    assert groq_board["identifier"] == "groq"
    assert groq_board["enabled"] is True
