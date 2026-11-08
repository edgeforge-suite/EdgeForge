from scripts.smoke.boot41_evidence_supplement import current_dispositions, historical_dispositions


def finding():
    return {
        "coordinate": "tools.jackson.core:jackson-core", "version": "3.1.5", "id": "SYNTHETIC-1",
        "aliases": ["ALIAS-FIRST"], "scopes": ["compile"], "usages": ["production"],
        "impact": "production-or-build", "cases": ["crud-h2-j17"],
        "observations": [{"finding": {"aliases": [alias], "fixed_versions": ["3.1.7"]}}
                         for alias in ("ALIAS-FIRST", "ALIAS-SECOND")],
    }


def test_historical_mapping_uses_all_pass_aliases_without_claiming_a_fix():
    old = {"coordinate": "com.fasterxml.jackson.core:jackson-core", "version": "2.17.2",
           "id": "ALIAS-SECOND", "scopes": ["compile"], "cases": ["old-case"]}
    rows = historical_dispositions([old], [finding()], {
        "tools.jackson.core:jackson-core": {"3.1.5": {"crud-h2-j17"}}
    })
    assert rows[0]["current_advisory_matches"][0]["status"] == "OPEN"
    assert rows[0]["current_resolved_coordinates"][0]["version"] == "3.1.5"
    assert "does not prove advisory-range equivalence" in rows[0]["decision"]


def test_current_decisions_preserve_alias_conflicts_and_open_owner_decision():
    row = current_dispositions([finding()])[0]
    assert row["status"] == "OPEN" and row["owner"] == "Engine maintainer"
    assert row["aliases"] == ["ALIAS-FIRST", "ALIAS-SECOND"]
    assert row["metadata_conflicts"]["aliases"] == [["ALIAS-FIRST"], ["ALIAS-SECOND"]]
    assert row["version_candidate_attempts"] == 0
