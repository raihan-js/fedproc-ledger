from fedproc_ledger.registry.build import REG_CODE, _sort_key, x52_parts


def test_natural_section_order_with_mixed_pieces():
    nums = ["52.219-14", "52.219-9", "52.204-1", "252.204-7012", "52.212-5", "52.2xx-1", "52.219-9a", "52.1"]
    got = sorted(nums, key=_sort_key)
    assert got.index("52.219-9") < got.index("52.219-14") and got.index("52.1") < got.index("52.204-1")
    assert got.index("52.204-1") < got.index("52.212-5") < got.index("52.219-9")


def test_x52_parts_come_from_the_structure_with_their_chapter():
    tree = {
        "type": "title", "identifier": "48",
        "children": [
            {"type": "chapter", "identifier": "1", "label": " Chapter 1\u2014Federal Acquisition Regulation", "children": [
                {"type": "part", "identifier": "52", "label": "Part 52"}, {"type": "part", "identifier": "51", "label": "Part 51"}]},
            {"type": "chapter", "identifier": "14", "label": " Chapter 14\u2014Department of the Interior", "children": [
                {"type": "part", "identifier": "1452", "label": "Part 1452"}]},
        ],
    }  # fmt: skip
    parts = x52_parts(tree)
    assert [(p["part"], p["regulation"]) for p in parts] == [("52", "FAR"), ("1452", "CH14")]
    assert parts[1]["regulation_name"].strip().endswith("Department of the Interior") and "1" in REG_CODE
