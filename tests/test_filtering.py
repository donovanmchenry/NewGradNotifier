from newgrad_notifier.collectors.relevance import is_relevant_role, location_allowed
from newgrad_notifier.config.settings import load_settings


def test_filtering_rejects_internships_and_non_us_roles():
    settings = load_settings("config/local_dev.toml")

    assert is_relevant_role("Software Engineering Intern", "Summer internship role", settings) is False
    assert is_relevant_role("Embedded Software Engineer", "Firmware and hardware focus", settings) is False
    assert is_relevant_role("Senior Software Engineer", "Backend platform role", settings) is False
    assert is_relevant_role("Software Engineer", "General SWE role for 4+ years of experience", settings) is False
    assert is_relevant_role("Software Engineer", "Entry-level role for 2027 graduates in the United States", settings) is True
    assert location_allowed("Toronto, ON, Canada", settings) is False
    assert location_allowed("Remote - Canada", settings) is False
    assert location_allowed("Seattle, WA", settings) is True
    assert location_allowed("Remote, United States", settings) is True
