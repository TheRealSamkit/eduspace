"""
Test suite validating route stability, endpoint integrity, and URL mapping invariants.

Asserts:
- The route table (URL rule and HTTP methods) matches tests/route_snapshot.json identically.
- Every url_for call across all Jinja templates and static JS files maps to a registered endpoint in app.url_map.
"""

import json
import os
import sys
import re
import glob
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app


@pytest.fixture
def test_app():
    """Create test app instance."""
    app = create_app({'TESTING': True, 'SECRET_KEY': 'route-integrity-test'})
    return app


def test_route_table_matches_snapshot(test_app):
    """Assert that the set of (URL rule, methods) is IDENTICAL to the snapshot."""
    snapshot_path = os.path.join(os.path.dirname(__file__), 'route_snapshot.json')
    with open(snapshot_path, 'r', encoding='utf-8') as f:
        snapshot_data = json.load(f)

    # Current routes from app.url_map
    current_routes = set()
    for rule in test_app.url_map.iter_rules():
        rule_str = str(rule.rule)
        methods = frozenset(rule.methods - {'OPTIONS', 'HEAD'})
        current_routes.add((rule_str, methods))

    snapshot_routes = set()
    for item in snapshot_data:
        rule_str = item['rule']
        methods = frozenset(item['methods'])
        snapshot_routes.add((rule_str, methods))

    assert current_routes == snapshot_routes, (
        f"Route table changed!\n"
        f"Added: {current_routes - snapshot_routes}\n"
        f"Removed: {snapshot_routes - current_routes}"
    )


def test_all_template_and_js_url_for_endpoints_exist(test_app):
    """Assert that every url_for call in templates and JS references a valid registered endpoint."""
    registered_endpoints = {rule.endpoint for rule in test_app.url_map.iter_rules()}
    # Also include static if registered
    registered_endpoints.add('static')

    files_to_scan = []
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    files_to_scan.extend(glob.glob(os.path.join(base_dir, 'templates', '**', '*.html'), recursive=True))
    files_to_scan.extend(glob.glob(os.path.join(base_dir, 'static', '**', '*.js'), recursive=True))

    pattern = re.compile(r"url_for\(['\"]([a-zA-Z0-9_\.]+)['\"]")

    missing = []
    for filepath in files_to_scan:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        matches = pattern.findall(content)
        for ep in matches:
            if ep not in registered_endpoints:
                missing.append((os.path.basename(filepath), ep))

    assert not missing, f"Found stale url_for calls with unregistered endpoints: {missing}"
