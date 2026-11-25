from um_charging import m11_leftovers as study


def test_unsettled_point_keeps_its_rank_when_only_a_lower_bound_exists():
    rows=[dict(design=d,basis="new",caps=[40,20],status=s,lower=l,upper=u)
          for d,s,l,u in (("x","billed",100,110),("y","unresolved",95,None),("z","billed",125,130))]
    ranks={r["design"]:(r["rank_best"],r["rank_worst"]) for r in study.rank(rows)}
    assert ranks=={"x":(1,2),"y":(1,3),"z":(2,3)}


def test_signed_cost_difference_and_missing_upper_bound():
    assert study.difference((10,12),(7,8))==[2,5]
    assert study.difference((10,12),(15,None))==[None,-3]
