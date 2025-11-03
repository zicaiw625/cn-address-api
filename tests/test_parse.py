from app.parser.address_parser import parse_address


def test_parse_basic():
    raw = "浙江省杭州市滨江区长河街道江南大道1234号XX科技园5幢402室 张三 15900001234 310052"
    result = parse_address(raw).model_dump()

    assert result["province"] == "浙江省"
    assert result["city"] == "杭州市"
    assert result["district"] == "滨江区"

    # street should still contain 长河街道 / 江南大道 etc.
    assert "江南大道" in (result["street"] or "")

    # phone extracted
    assert result["phone"] == "15900001234"

    # recipient extracted
    assert result["recipient"] == "张三"

    # has postal code (either from text or metadata)
    assert result["postal_code"] == "310052"

    # deliverable heuristic should be True
    assert result["deliverable"] is True

    assert 0.5 <= result["confidence"] <= 1.0


def test_parse_without_recipient():
    raw = "北京市朝阳区建国路88号"
    result = parse_address(raw).model_dump()

    assert result["province"] == "北京市"
    assert result["city"] == "北京市"
    assert result["district"] == "朝阳区"

    # ensure street content preserved when no explicit recipient is present
    assert result["street"] == "建国路88号"
    assert result["recipient"] is None
