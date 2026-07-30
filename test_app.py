"""Unit tests for app.py core functions (Tasks 1-3)."""

import pytest
from app import (
    parse_comma_separated,
    validate_inputs,
    generate_color_codes,
    generate_variations,
    build_dataframe,
    PLATFORM_CONFIGS,
)


# ─── parse_comma_separated ────────────────────────────────────────────────────


class TestParseCommaSeparated:
    def test_basic_split(self):
        assert parse_comma_separated("Red, Blue, Green") == ["Red", "Blue", "Green"]

    def test_trims_whitespace(self):
        assert parse_comma_separated("  Red , Blue  ,Green  ") == ["Red", "Blue", "Green"]

    def test_removes_empty_strings(self):
        assert parse_comma_separated("Red,,Blue,,,Green") == ["Red", "Blue", "Green"]

    def test_trailing_comma(self):
        assert parse_comma_separated("Red, Blue,") == ["Red", "Blue"]

    def test_deduplicates_preserving_order(self):
        assert parse_comma_separated("Red, Blue, Red, Green, Blue") == ["Red", "Blue", "Green"]

    def test_empty_input(self):
        assert parse_comma_separated("") == []

    def test_whitespace_only_input(self):
        assert parse_comma_separated("   ,  ,  ") == []

    def test_single_value(self):
        assert parse_comma_separated("Red") == ["Red"]


# ─── validate_inputs ──────────────────────────────────────────────────────────


class TestValidateInputs:
    def _valid_form_data(self):
        return {
            "brand_name": "TestBrand",
            "product_category": "T-Shirt",
            "fabric_material": "Cotton",
            "description": "A great product",
            "base_style_code": "TSH-001",
            "price": 499.0,
            "gst_percent": 5.0,
            "colors_raw": "Red, Blue",
            "sizes_raw": "S, M, L",
        }

    def test_valid_input_returns_no_errors(self):
        errors = validate_inputs(self._valid_form_data())
        assert errors == []

    def test_blank_brand_name(self):
        data = self._valid_form_data()
        data["brand_name"] = "   "
        errors = validate_inputs(data)
        assert any("Brand Name" in e for e in errors)

    def test_missing_field(self):
        data = self._valid_form_data()
        data["brand_name"] = ""
        errors = validate_inputs(data)
        assert any("Brand Name" in e for e in errors)

    def test_negative_price(self):
        data = self._valid_form_data()
        data["price"] = -10
        errors = validate_inputs(data)
        assert any("Price" in e for e in errors)

    def test_zero_price(self):
        data = self._valid_form_data()
        data["price"] = 0
        errors = validate_inputs(data)
        assert any("Price" in e for e in errors)

    def test_non_numeric_price(self):
        data = self._valid_form_data()
        data["price"] = "abc"
        errors = validate_inputs(data)
        assert any("Price" in e for e in errors)

    def test_negative_gst(self):
        data = self._valid_form_data()
        data["gst_percent"] = -1
        errors = validate_inputs(data)
        assert any("GST" in e for e in errors)

    def test_zero_gst_is_valid(self):
        data = self._valid_form_data()
        data["gst_percent"] = 0
        errors = validate_inputs(data)
        assert not any("GST" in e for e in errors)

    def test_empty_colors(self):
        data = self._valid_form_data()
        data["colors_raw"] = ""
        errors = validate_inputs(data)
        assert any("color" in e.lower() or "size" in e.lower() for e in errors)

    def test_empty_sizes(self):
        data = self._valid_form_data()
        data["sizes_raw"] = ""
        errors = validate_inputs(data)
        assert any("color" in e.lower() or "size" in e.lower() for e in errors)

    def test_multiple_errors_collected(self):
        data = self._valid_form_data()
        data["brand_name"] = ""
        data["price"] = -5
        data["colors_raw"] = ""
        errors = validate_inputs(data)
        assert len(errors) >= 3


# ─── generate_color_codes ─────────────────────────────────────────────────────


class TestGenerateColorCodes:
    def test_basic_generation(self):
        codes = generate_color_codes("TSH-001", ["Black", "Red", "Blue"])
        assert codes["Black"] == "TSH-001-BLA"
        assert codes["Red"] == "TSH-001-RED"
        assert codes["Blue"] == "TSH-001-BLU"

    def test_collision_handling(self):
        codes = generate_color_codes("TSH-001", ["Black", "Blanc"])
        assert codes["Black"] == "TSH-001-BLA"
        assert codes["Blanc"] == "TSH-001-BLA2"

    def test_triple_collision(self):
        codes = generate_color_codes("X", ["Black", "Blanc", "Blaze"])
        assert codes["Black"] == "X-BLA"
        assert codes["Blanc"] == "X-BLA2"
        assert codes["Blaze"] == "X-BLA3"

    def test_all_codes_unique(self):
        codes = generate_color_codes("CODE", ["Red", "Rose", "Ruby", "Rust"])
        values = list(codes.values())
        assert len(values) == len(set(values))

    def test_short_color_name(self):
        codes = generate_color_codes("X", ["AB"])
        assert codes["AB"] == "X-AB"

    def test_single_char_color(self):
        codes = generate_color_codes("X", ["R"])
        assert codes["R"] == "X-R"


# ─── generate_variations ──────────────────────────────────────────────────────


class TestGenerateVariations:
    def _form_data(self):
        return {
            "brand_name": "TestBrand",
            "product_category": "T-Shirt",
            "price": 499.0,
            "gst_percent": 5.0,
            "fabric_material": "Cotton",
            "description": "Great product",
            "base_style_code": "TSH-001",
            "colors": ["Black", "Red"],
            "sizes": ["S", "M", "L"],
        }

    def test_cartesian_product_count(self):
        form = self._form_data()
        codes = generate_color_codes(form["base_style_code"], form["colors"])
        variations = generate_variations(form, codes)
        assert len(variations) == 2 * 3  # 2 colors × 3 sizes

    def test_ordering_color_first(self):
        form = self._form_data()
        codes = generate_color_codes(form["base_style_code"], form["colors"])
        variations = generate_variations(form, codes)
        # First 3 should be Black, next 3 should be Red
        assert all(v["color"] == "Black" for v in variations[:3])
        assert all(v["color"] == "Red" for v in variations[3:])

    def test_size_order_within_color(self):
        form = self._form_data()
        codes = generate_color_codes(form["base_style_code"], form["colors"])
        variations = generate_variations(form, codes)
        sizes_for_black = [v["size"] for v in variations[:3]]
        assert sizes_for_black == ["S", "M", "L"]

    def test_sku_format(self):
        form = self._form_data()
        codes = generate_color_codes(form["base_style_code"], form["colors"])
        variations = generate_variations(form, codes)
        first = variations[0]
        assert first["sku"] == "TSH-001-BLA-S"

    def test_product_title_format(self):
        form = self._form_data()
        codes = generate_color_codes(form["base_style_code"], form["colors"])
        variations = generate_variations(form, codes)
        first = variations[0]
        assert first["product_title"] == "TestBrand T-Shirt - Black - S"

    def test_all_skus_unique(self):
        form = self._form_data()
        codes = generate_color_codes(form["base_style_code"], form["colors"])
        variations = generate_variations(form, codes)
        skus = [v["sku"] for v in variations]
        assert len(skus) == len(set(skus))

    def test_variation_contains_all_fields(self):
        form = self._form_data()
        codes = generate_color_codes(form["base_style_code"], form["colors"])
        variations = generate_variations(form, codes)
        expected_keys = {"style_code", "sku", "product_title", "price", "gst", "fabric", "description", "color", "size"}
        for v in variations:
            assert set(v.keys()) == expected_keys


# ─── PLATFORM_CONFIGS sanity ──────────────────────────────────────────────────


class TestPlatformConfigs:
    def test_meesho_has_correct_headers(self):
        assert PLATFORM_CONFIGS["Meesho"]["headers"] == [
            'Style Code', 'SKU ID', 'Product Title', 'Price',
            'GST %', 'Fabric', 'Description', 'Color', 'Size'
        ]

    def test_flipkart_has_correct_headers(self):
        assert PLATFORM_CONFIGS["Flipkart"]["headers"] == [
            'Group ID / Style Code', 'Seller SKU ID', 'Product Name',
            'Selling Price', 'GST Rate', 'Material', 'Key Features', 'Color', 'Size'
        ]

    def test_field_maps_cover_all_internal_fields(self):
        expected_fields = {"style_code", "sku", "product_title", "price", "gst", "fabric", "description", "color", "size"}
        for platform in PLATFORM_CONFIGS:
            assert set(PLATFORM_CONFIGS[platform]["field_map"].keys()) == expected_fields


# ─── build_dataframe ──────────────────────────────────────────────────────────


class TestBuildDataframe:
    def _sample_variations(self):
        return [
            {
                "style_code": "TSH-001-BLA",
                "sku": "TSH-001-BLA-S",
                "product_title": "TestBrand T-Shirt - Black - S",
                "price": 499.0,
                "gst": 5.0,
                "fabric": "Cotton",
                "description": "Great product",
                "color": "Black",
                "size": "S",
            },
            {
                "style_code": "TSH-001-BLA",
                "sku": "TSH-001-BLA-M",
                "product_title": "TestBrand T-Shirt - Black - M",
                "price": 499.0,
                "gst": 5.0,
                "fabric": "Cotton",
                "description": "Great product",
                "color": "Black",
                "size": "M",
            },
        ]

    def test_meesho_columns_match_headers(self):
        df = build_dataframe(self._sample_variations(), "Meesho")
        assert list(df.columns) == PLATFORM_CONFIGS["Meesho"]["headers"]

    def test_flipkart_columns_match_headers(self):
        df = build_dataframe(self._sample_variations(), "Flipkart")
        assert list(df.columns) == PLATFORM_CONFIGS["Flipkart"]["headers"]

    def test_meesho_field_mapping(self):
        df = build_dataframe(self._sample_variations(), "Meesho")
        row = df.iloc[0]
        assert row["Style Code"] == "TSH-001-BLA"
        assert row["SKU ID"] == "TSH-001-BLA-S"
        assert row["Product Title"] == "TestBrand T-Shirt - Black - S"
        assert row["Price"] == 499.0
        assert row["GST %"] == 5.0
        assert row["Fabric"] == "Cotton"
        assert row["Description"] == "Great product"
        assert row["Color"] == "Black"
        assert row["Size"] == "S"

    def test_flipkart_field_mapping(self):
        df = build_dataframe(self._sample_variations(), "Flipkart")
        row = df.iloc[0]
        assert row["Group ID / Style Code"] == "TSH-001-BLA"
        assert row["Seller SKU ID"] == "TSH-001-BLA-S"
        assert row["Product Name"] == "TestBrand T-Shirt - Black - S"
        assert row["Selling Price"] == 499.0
        assert row["GST Rate"] == 5.0
        assert row["Material"] == "Cotton"
        assert row["Key Features"] == "Great product"
        assert row["Color"] == "Black"
        assert row["Size"] == "S"

    def test_row_count_matches_input(self):
        df = build_dataframe(self._sample_variations(), "Meesho")
        assert len(df) == 2

    def test_empty_variations_returns_empty_dataframe(self):
        df = build_dataframe([], "Meesho")
        assert len(df) == 0
        assert list(df.columns) == PLATFORM_CONFIGS["Meesho"]["headers"]

    def test_column_order_is_exact(self):
        """Columns must be in the exact order defined by platform headers."""
        df = build_dataframe(self._sample_variations(), "Flipkart")
        expected_order = PLATFORM_CONFIGS["Flipkart"]["headers"]
        assert list(df.columns) == expected_order
