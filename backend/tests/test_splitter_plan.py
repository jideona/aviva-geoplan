from app.domain.splitter_plan import (SplitArchitecture, SplitStage, options,
                                      plan)

# The real Aviva stock.
STOCK = {4: 0, 8: 78, 32: 18}


def test_two_stage_1_32_needs_the_primary_that_stock_lacks():
    arch = SplitArchitecture(SplitStage.TWO, 4, 8)
    result = plan(arch, 16, STOCK)
    assert result.architecture.overall == 32
    assert not result.zero_purchase
    gaps = {l.ratio: l.gap for l in result.lines}
    assert gaps[4] > 0                       # zero 1:4 in stock


def test_single_stage_1_32_is_nearly_covered_by_stock():
    arch = SplitArchitecture(SplitStage.SINGLE, 32, 1)
    # 16 active + small spare against 18 in stock.
    result = plan(arch, 16, STOCK, spare_ratio=0.1)
    assert result.endpoints == 512
    assert all(l.ratio == 32 for l in result.lines)


def test_options_enumerates_and_flags_purchase_need():
    opts = options(16, STOCK)
    assert any(o.architecture.overall == 32 for o in opts)
    assert any(o.architecture.overall == 64 for o in opts)
    for o in opts:
        # a plan is zero-purchase only if every line's gap is zero
        assert o.zero_purchase == all(l.gap == 0 for l in o.lines)


def test_endpoints_equal_ports_times_overall_split():
    result = plan(SplitArchitecture(SplitStage.TWO, 4, 8), 16, STOCK)
    assert result.endpoints == 16 * 32
