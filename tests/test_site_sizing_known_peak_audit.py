from dataclasses import replace
from types import SimpleNamespace

import pytest

from um_charging import site_sizing as ss
from um_charging.site_sizing_bounds import AnnualBillBounds
from um_charging.site_sizing_known_peak_audit import Archive, _holdout_purchase
from um_charging.site_sizing_screen_evidence import ArchiveWeek
from um_charging.site_sizing_screen_run import _proof_data


def test_holdout_excludes_both_target_and_reused_scope_including_duplicate_proofs():
    week, caps = "2021-10-04", (15, 0)
    target = ss.Design(1, 20, 0)
    borrowed = ss.Design(1, 30, 0)
    held = ArchiveWeek(week, borrowed, caps, "certified", 15., 15., {}, "one", "hash", "source")
    independent = replace(held, caps=(20, 0), lower_eur=13., proof="independent")
    other_records = [held, replace(held, proof="duplicate"), replace(held, design=target, proof="target"),
                     independent]
    archive = SimpleNamespace(bounds=AnnualBillBounds.__new__(AnnualBillBounds), ranking_by_week={week: other_records})
    point = SimpleNamespace(design=target, caps=caps)
    selected = _holdout_purchase(archive, point, held)
    assert selected.proof == independent.proof
    assert selected.lower_eur == 13. - ss.EPS


def test_holdout_falls_back_when_only_the_held_physical_scope_is_available():
    week, caps = "2021-10-04", (15, 0)
    target = ss.Design(1, 20, 0)
    held = ArchiveWeek(week, target, caps, "certified", 15., 15., {}, "held", "hash", "source")
    bounds = AnnualBillBounds.__new__(AnnualBillBounds)
    bounds.weekly_floor = {week: -20.}
    archive = SimpleNamespace(bounds=bounds, ranking_by_week={week: [held]})
    result = _holdout_purchase(archive, SimpleNamespace(design=target, caps=caps), held)
    assert result.proof is None and result.lower_eur == -20. - ss.EPS


def test_an_audited_timeout_incumbent_cannot_fix_the_peak():
    design, caps = ss.Design(1, 20, 20), (15, 20)
    audit = dict(passed=True, used_plugs={ss.PORT: 1}, site_peak_kw={ss.PORT: 15., ss.WAREHOUSE: 20.})
    record = ArchiveWeek("2021-10-04", design, caps, "unresolved", 2., 4., audit, "p", "hash", "source")
    archive = Archive(SimpleNamespace(cases={design.label: design}), None, {}, {}, {}, {"p": record},
                      {}, {}, None, {}, {"p"}, verified_meters={("p", design)})
    row = dict(kind="ranking", design=design.label, caps_kw=caps, weeks=[_proof_data(record)])
    with pytest.raises(ValueError, match="failed week cannot fix"):
        archive.accepted(row)


def test_quote_only_meter_is_rejected_if_a_ranking_row_cites_it():
    design, caps = ss.Design(1, 50, 0), (25, 0)
    record = ArchiveWeek("2021-10-04", design, caps, "bounded", 2., 2.03, {}, "quote", "hash", "source")
    archive = Archive(SimpleNamespace(cases={design.label: design}), None, {}, {}, {}, {"quote": record},
                      {}, {}, None, {}, set())
    row = dict(kind="ranking", design=design.label, caps_kw=caps, weeks=[_proof_data(record)])
    with pytest.raises(ValueError, match="quote-only weekly proof"):
        archive.accepted(row)
