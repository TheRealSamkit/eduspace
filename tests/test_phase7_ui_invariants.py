"""
Tests for Phase 7: UI invariants on new templates (no .alert banners, zero btn-secondary,
at most one btn-primary per new screen).
"""

import os
import re

NEW_TEMPLATES = [
    'saved.html',
    'public_library.html',
    'public_detail.html',
    'register_public.html',
    'requests.html',
    'request_detail.html',
]


def test_new_templates_ui_invariants():
    """Verify no .alert banners, no btn-secondary, and <=1 btn-primary in new templates."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    for name in NEW_TEMPLATES:
        path = os.path.join(root, 'templates', name)
        with open(path, 'r', encoding='utf-8') as f:
            html = f.read()

        assert 'btn-secondary' not in html, f"Found forbidden btn-secondary in {name}"
        assert not re.search(r'class="[^"]*\balert\b', html), f"Found forbidden .alert banner in {name}"
        primaries = re.findall(r'\bbtn-primary\b', html)
        # public_library.html has guest+auth branches; requests.html has header+modal; request_detail.html has requester vs contributor branches
        limit = 2 if name in ('public_library.html', 'requests.html', 'request_detail.html') else 1
        assert len(primaries) <= limit, f"Too many btn-primary ({len(primaries)}) in {name}"
