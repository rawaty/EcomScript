"""Unit tests for platform detection, field aliases, and helpers."""

import pytest
from app import (
    parse_csv,
    parse_comma_separated,
    detect_platform,
    resolve_fields,
    programmatic_field_set,
    auto_field_set,
    scrub_restricted,
    restricted_keywords_for,
    PLATFORM_ALIASES,
)
from qc_checker import run_qc_check


# ─── parse_csv / parse_comma_separated ────────────────────────────────────────


class TestParseCsv:
    def test_basic_split(self):
        assert parse_csv("Red, Blue, Green") == ["Red", "Blue", "Green"]

    def test_trims_whitespace(self):
        assert parse_csv("  Red , Blue  ,Green  ") == ["Red", "Blue", "Green"]

    def test_removes_empty_strings(self):
        assert parse_csv("Red,,Blue,,,Green") == ["Red", "Blue", "Green"]

    def test_trailing_comma(self):
        assert parse_csv("Red, Blue,") == ["Red", "Blue"]

    def test_deduplicates_preserving_order(self):
        assert parse_csv("Red, Blue, Red, Green, Blue") == ["Red", "Blue", "Green"]

    def test_empty_input(self):
        assert parse_csv("") == []

    def test_whitespace_only_input(self):
        assert parse_csv("   ,  ,  ") == []

    def test_single_value(self):
        assert parse_csv("Red") == ["Red"]

    def test_alias(self):
        assert parse_comma_separated is parse_csv


# ─── detect_platform ──────────────────────────────────────────────────────────


class TestDetectPlatform:
    def test_meesho_headers(self):
        col_map = {
            "Product Name": 1,
            "SKU ID": 2,
            "Product ID / Style ID": 3,
            "Meesho Price": 4,
            "Variation": 5,
        }
        assert detect_platform(col_map) == "Meesho"

    def test_flipkart_headers(self):
        col_map = {
            "Product Name": 1,
            "Seller SKU ID": 2,
            "Group ID / Style Code": 3,
            "Selling Price": 4,
            "Size": 5,
            "Key Features": 6,
        }
        assert detect_platform(col_map) == "Flipkart"

    def test_flipkart_wins_on_more_hits(self):
        col_map = {
            "Seller SKU ID": 1,
            "Selling Price": 2,
            "Group ID / Style Code": 3,
            "Product Name": 4,  # shared-ish
        }
        assert detect_platform(col_map) == "Flipkart"

    def test_unknown_defaults_meesho(self):
        assert detect_platform({"Foo": 1, "Bar": 2}) == "Meesho"


# ─── resolve_fields ───────────────────────────────────────────────────────────


class TestResolveFields:
    def test_meesho_resolution(self):
        col_map = {
            "Product Name": 1,
            "SKU ID": 2,
            "Product ID / Style ID": 3,
            "Meesho Price": 4,
            "Wrong/Defective Returns Price": 5,
            "Variation": 6,
            "Group ID": 7,
            "Product Description": 8,
            "Brand Name": 9,
            "Color": 10,
            "Image 1 (Front)": 11,
            "Image 2": 12,
            "MRP": 13,
        }
        fields = resolve_fields(col_map, "Meesho")
        assert fields["product_name"] == "Product Name"
        assert fields["sku"] == "SKU ID"
        assert fields["style_id"] == "Product ID / Style ID"
        assert fields["price"] == "Meesho Price"
        assert fields["wd_price"] == "Wrong/Defective Returns Price"
        assert fields["variation"] == "Variation"
        assert fields["image1"] == "Image 1 (Front)"

    def test_flipkart_resolution(self):
        col_map = {
            "Product Name": 1,
            "Seller SKU ID": 2,
            "Group ID / Style Code": 3,
            "Selling Price": 4,
            "Size": 5,
            "Key Features": 6,
            "Brand": 7,
            "Color": 8,
            "Main Image URL": 9,
            "MRP": 10,
            "Material": 11,
        }
        fields = resolve_fields(col_map, "Flipkart")
        assert fields["sku"] == "Seller SKU ID"
        assert fields["style_id"] == "Group ID / Style Code"
        assert fields["price"] == "Selling Price"
        assert fields["variation"] == "Size"
        assert fields["description"] == "Key Features"
        assert fields["brand"] == "Brand"
        assert fields["fabric"] == "Material"
        assert fields["image1"] == "Main Image URL"
        assert "wd_price" not in fields

    def test_case_insensitive_fallback(self):
        col_map = {"selling price": 1, "seller sku id": 2}
        fields = resolve_fields(col_map, "Flipkart")
        assert fields["price"] == "selling price"
        assert fields["sku"] == "seller sku id"

    def test_auto_and_programmatic_sets(self):
        fields = {
            "product_name": "Product Name",
            "sku": "Seller SKU ID",
            "style_id": "Group ID / Style Code",
            "brand": "Brand",
            "color": "Color",
            "variation": "Size",
        }
        assert auto_field_set(fields) == {
            "Product Name", "Seller SKU ID", "Group ID / Style Code"
        }
        prog = programmatic_field_set(fields)
        assert "Seller SKU ID" in prog
        assert "Size" in prog

    def test_platform_aliases_keys(self):
        assert set(PLATFORM_ALIASES.keys()) == {"Meesho", "Flipkart"}
        for platform, roles in PLATFORM_ALIASES.items():
            assert "product_name" in roles
            assert "sku" in roles
            assert "price" in roles


# ─── scrub / restricted keywords ──────────────────────────────────────────────


class TestRestrictedKeywords:
    def test_meesho_scrubs_flipkart_word(self):
        text = scrub_restricted("Buy on Flipkart now", "Meesho")
        assert "Flipkart" not in text

    def test_flipkart_allows_flipkart_word(self):
        # Flipkart list does not ban "Flipkart"
        assert "Flipkart" not in restricted_keywords_for("Flipkart")
        text = scrub_restricted("Great Flipkart style kurti", "Flipkart")
        assert "Flipkart" in text

    def test_flipkart_scrubs_meesho(self):
        text = scrub_restricted("Also on Meesho", "Flipkart")
        assert "Meesho" not in text


# ─── QC platform awareness ────────────────────────────────────────────────────


class TestQcChecker:
    def _meesho_fields(self):
        return {
            "product_name": "Product Name",
            "sku": "SKU ID",
            "style_id": "Product ID / Style ID",
            "variation": "Variation",
            "group_id": "Group ID",
            "brand": "Brand Name",
            "price": "Meesho Price",
            "wd_price": "Wrong/Defective Returns Price",
            "mrp": "MRP",
            "description": "Product Description",
            "image1": "Image 1 (Front)",
        }

    def _flipkart_fields(self):
        return {
            "product_name": "Product Name",
            "sku": "Seller SKU ID",
            "style_id": "Group ID / Style Code",
            "variation": "Size",
            "group_id": "Group ID",
            "brand": "Brand",
            "price": "Selling Price",
            "mrp": "MRP",
            "description": "Key Features",
            "image1": "Main Image URL",
        }

    def test_meesho_flags_restricted_keyword(self):
        fields = self._meesho_fields()
        col_map = {v: i for i, v in enumerate(fields.values(), 1)}
        rows = [{
            "Product Name": "Comfort Black Kurti",
            "SKU ID": "S1",
            "Product ID / Style ID": "ST1",
            "Variation": "M",
            "Group ID": "1",
            "Brand Name": "Test",
            "Meesho Price": 199,
            "MRP": 499,
            "Image 1 (Front)": "https://cdn.example.com/a.jpg",
        }]
        errors, _ = run_qc_check(rows, col_map, platform="Meesho", fields=fields)
        assert any("Restricted keyword" in e["message"] for e in errors)

    def test_flipkart_does_not_error_on_meesho_keyword_comfort(self):
        fields = self._flipkart_fields()
        col_map = {v: i for i, v in enumerate(fields.values(), 1)}
        rows = [{
            "Product Name": "Comfort Black Kurti",
            "Seller SKU ID": "S1",
            "Group ID / Style Code": "ST1",
            "Size": "M",
            "Group ID": "1",
            "Brand": "Test",
            "Selling Price": 199,
            "MRP": 499,
            "Main Image URL": "https://cdn.example.com/a.jpg",
        }]
        errors, _ = run_qc_check(rows, col_map, platform="Flipkart", fields=fields)
        assert not any("Restricted keyword" in e["message"] for e in errors)

    def test_flipkart_price_vs_mrp(self):
        fields = self._flipkart_fields()
        col_map = {v: i for i, v in enumerate(fields.values(), 1)}
        rows = [{
            "Product Name": "Black Kurti",
            "Seller SKU ID": "S1",
            "Group ID / Style Code": "ST1",
            "Size": "M",
            "Group ID": "1",
            "Brand": "Test",
            "Selling Price": 600,
            "MRP": 499,
            "Main Image URL": "https://cdn.example.com/a.jpg",
        }]
        errors, _ = run_qc_check(rows, col_map, platform="Flipkart", fields=fields)
        assert any("must be less than MRP" in e["message"] for e in errors)

    def test_empty_rows(self):
        errors, warnings = run_qc_check([], {}, platform="Meesho", fields={})
        assert errors
        assert errors[0]["error_type"] == "CRITICAL"
