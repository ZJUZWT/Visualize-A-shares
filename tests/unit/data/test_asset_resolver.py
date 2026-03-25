from engine.data.asset_resolver import AssetResolver


def test_resolve_cn_stock():
    resolver = AssetResolver()
    asset = resolver.resolve("600519")
    assert asset.market == "cn"
    assert asset.asset_type == "stock"


def test_resolve_hk_stock():
    resolver = AssetResolver()
    asset = resolver.resolve("00700")
    assert asset.market == "hk"
    assert asset.asset_type == "stock"


def test_resolve_us_stock():
    resolver = AssetResolver()
    asset = resolver.resolve("AAPL")
    assert asset.market == "us"
    assert asset.asset_type == "stock"


def test_resolve_fund():
    resolver = AssetResolver()
    asset = resolver.resolve("161725")
    assert asset.market == "fund"
    assert asset.asset_type == "fund"


def test_resolve_future():
    resolver = AssetResolver()
    asset = resolver.resolve("CL")
    assert asset.market == "futures"
    assert asset.asset_type == "future"
