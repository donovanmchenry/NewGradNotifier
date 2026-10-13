from __future__ import annotations

import json
from pathlib import Path

import pytest

from newgrad_notifier.company_watch import classify_posting, watch_company
from newgrad_notifier.config.settings import load_settings


def posting(key='job-1', title='Software Engineer - New Grad 2027', **overrides):
    return {'id': key, 'title': title, 'location': 'U.S. Remote',
            'descriptionHtml': '<p>Build backend services.</p>',
            'publishedAt': '2020-01-01T00:00:00Z',
            'applyUrl': f'https://jobs.ashbyhq.com/delinea/{key}/application', **overrides}


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('EMAIL_PROVIDER', 'console')
    monkeypatch.setenv('COMPANY_WATCH_ENABLED', 'true')
    monkeypatch.setenv('COMPANY_WATCH_STATE_PATH', str(tmp_path / 'state.json'))
    settings = load_settings('config/production.toml')
    settings.cache_dir = str(tmp_path / 'cache')
    settings.company_watch.board.api_url = str(tmp_path / 'board.json')
    settings.thresholds.max_digest_jobs = 1
    settings.thresholds.digest_min_fit = 100
    return settings


class Sender:
    def __init__(self, fail_at=None):
        self.messages = []
        self.fail_at = fail_at

    def send(self, subject, body_text, recipient, **kwargs):
        if len(self.messages) == self.fail_at:
            raise RuntimeError('email failed')
        self.messages.append((subject, body_text, kwargs['idempotency_key']))


def run(settings, postings, sender):
    Path(settings.company_watch.board.api_url).write_text(json.dumps({'jobs': postings}))
    return watch_company(settings, sender=sender)


def test_uncapped_alerts_ignore_scores_and_age_and_dedupe(settings):
    sender = Sender()
    postings = [posting(str(i)) for i in range(10)] + [posting('generic', 'Software Engineer')]
    result = run(settings, postings, sender)
    assert result.notified_jobs == 11
    assert 'Eligibility unclear' in sender.messages[-1][1]
    assert run(settings, postings, sender).notified_jobs == 0
    assert len(sender.messages) == 11
    assert run(settings, postings + [posting('new')], sender).notified_jobs == 1


@pytest.mark.parametrize('item', [
    posting(title='Senior Software Engineer'),
    posting(title='Software Engineer II'),
    posting(title='Advanced Support Engineer I'),
    posting(title='Software Engineering Intern'),
    posting(title='Software Engineer Co-op'),
    posting(location='Remote - Mexico'),
    posting(location='Remote - Canada'),
    posting(descriptionHtml='<p>Requires 5+ years of experience.</p>'),
    posting(descriptionHtml='<p>For graduates in the class of 2026.</p>'),
    posting(isListed=False),
    posting(employmentType='Intern'),
])
def test_excludes_clear_mismatches(settings, item):
    assert classify_posting(item, settings) is None


@pytest.mark.parametrize('title', ['Junior Software Engineer', 'Associate Software Engineer',
                                   'Software Engineer I', 'Software Engineer', 'Backend Engineer'])
def test_keeps_junior_and_ambiguous_software_titles(settings, title):
    assert classify_posting(posting(title=title), settings) is not None


def test_partial_email_failure_saves_successful_notifications(settings):
    jobs = [posting('one'), posting('two')]
    first = Sender(fail_at=1)
    with pytest.raises(RuntimeError, match='email failed'):
        run(settings, jobs, first)
    state = json.loads(Path(settings.company_watch.state_path).read_text())
    assert set(state['seen']) == {'one'}
    retry = Sender()
    assert run(settings, jobs, retry).notified_jobs == 1
    assert retry.messages[0][2] != first.messages[0][2]
    assert run(settings, jobs, retry).notified_jobs == 0


def test_failed_email_keeps_stable_idempotency_key(settings):
    keys = []
    class FailedSender:
        def send(self, *_args, **kwargs):
            keys.append(kwargs['idempotency_key'])
            raise RuntimeError('delivery uncertain')
    for _ in range(2):
        with pytest.raises(RuntimeError):
            run(settings, [posting()], FailedSender())
    assert keys[0] == keys[1]
    assert json.loads(Path(settings.company_watch.state_path).read_text())['seen'] == {}


def test_network_and_corrupt_state_errors_do_not_send_or_reset_history(settings):
    sender = Sender()
    run(settings, [posting()], sender)
    path = Path(settings.company_watch.state_path)
    previous = path.read_text()
    class FailedClient:
        def get_json(self, *_args, **kwargs):
            raise RuntimeError('network failed')
    with pytest.raises(RuntimeError):
        watch_company(settings, client=FailedClient(), sender=sender)
    assert path.read_text() == previous
    path.write_text('{broken')
    with pytest.raises(ValueError):
        watch_company(settings, sender=sender)
    assert path.read_text() == '{broken'
    assert len(sender.messages) == 1


def test_board_errors_and_invalid_response_fail_closed(settings):
    class Client:
        def get_json(self, *_args, **kwargs):
            assert kwargs['use_cache'] is False
            return {'errors': [{'message': 'board unavailable'}]}
    with pytest.raises(ValueError):
        watch_company(settings, client=Client(), sender=Sender())
    assert not Path(settings.company_watch.state_path).exists()


def test_board_identity_prevents_mixing_notification_history(settings):
    run(settings, [], Sender())
    settings.company_watch.board.api_url += '.other'
    with pytest.raises(ValueError, match='different board'):
        watch_company(settings, sender=Sender())


def test_disabled_watch_never_fetches(settings):
    settings.company_watch.enabled = False
    assert watch_company(settings).total_jobs == 0
    assert not Path(settings.company_watch.state_path).exists()
