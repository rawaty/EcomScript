# Implementation Plan: Bulk Listing Generator

## Overview

Implement a single-file Python Streamlit web application (`app.py`) that generates bulk listing Excel files for Meesho and Flipkart. The implementation follows a bottom-up approach: core utility functions first, then variation generation logic, DataFrame/Excel output, and finally the Streamlit UI layer that wires everything together. A `test_app.py` file will contain property-based tests (Hypothesis) and unit tests.

## Tasks

- [x] 1. Set up project structure and platform configuration
  - [x] 1.1 Create requirements.txt and app.py with platform config
    - Create `requirements.txt` listing: streamlit, pandas, openpyxl
    - Create `app.py` with the `PLATFORM_CONFIGS` dictionary constant containing exact column headers and field mappings for both Meesho and Flipkart
    - Add necessary imports: streamlit, pandas, io, re, dataclasses
    - _Requirements: 7.1, 7.2, 4.1, 4.2, 4.3_

- [x] 2. Implement input parsing and validation
  - [x] 2.1 Implement `parse_comma_separated` function
    - Write function that splits input on commas, trims whitespace from each value, removes empty strings, and deduplicates while preserving first-occurrence order
    - Handle edge cases: trailing commas, consecutive commas, whitespace-only entries
    - _Requirements: 2.3, 2.4, 2.5_

  - [ ]* 2.2 Write property test for comma-separated parsing
    - **Property 1: Comma-separated parsing produces clean, unique output**
    - **Validates: Requirements 2.3, 2.4, 2.5**

  - [x] 2.3 Implement `validate_inputs` function
    - Validate required text fields (Brand Name, Product Category, Fabric/Material, Description, Base Style Code) are not blank/whitespace-only
    - Validate Price is a positive number
    - Validate GST % is non-negative
    - Validate Colors and Sizes parse to at least one value each
    - Return a list of all error messages (empty list means valid)
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [ ]* 2.4 Write property test for input validation rejection
    - **Property 8: Invalid inputs are rejected by validation**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

- [x] 3. Implement variation generation logic
  - [x] 3.1 Implement `generate_color_codes` function
    - Generate Color_Style_Code for each color using first 3 characters uppercased
    - Handle collision resolution: append incrementing numeric suffix starting from 2 for duplicate abbreviations
    - Return mapping of color name → Color_Style_Code
    - _Requirements: 3.2, 3.5_

  - [ ]* 3.2 Write property test for color code generation
    - **Property 3: Color code generation produces unique, correctly formatted codes**
    - **Validates: Requirements 3.2, 3.5**

  - [x] 3.3 Implement `generate_variations` function
    - Produce cartesian product of colors × sizes, ordered by color first then size within each color
    - Assign each row: Color_Style_Code, SKU (Color_Style_Code + "-" + SIZE uppercase), product title ("[Brand] [Category] - [Color] - [Size]")
    - Include price, GST, fabric, description, color, size in each variation dict
    - _Requirements: 3.1, 3.3, 3.4, 4.4_

  - [ ]* 3.4 Write property test for variation cartesian product
    - **Property 2: Variation generation produces correct cartesian product**
    - **Validates: Requirements 3.1, 3.4**

  - [ ]* 3.5 Write property test for SKU uniqueness
    - **Property 4: SKU generation produces unique identifiers**
    - **Validates: Requirements 3.3**

  - [ ]* 3.6 Write property test for product title format
    - **Property 5: Product title follows concatenation pattern**
    - **Validates: Requirements 4.4**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement DataFrame building and Excel generation
  - [x] 5.1 Implement `build_dataframe` function
    - Accept variation list and platform name
    - Map internal field names to platform-specific column headers using `PLATFORM_CONFIGS`
    - Return a Pandas DataFrame with columns in the exact platform-defined order
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [ ]* 5.2 Write property test for platform column mapping
    - **Property 6: Platform selection determines output columns**
    - **Validates: Requirements 1.3, 4.5**

  - [x] 5.3 Implement `generate_excel_bytes` function
    - Serialize DataFrame to .xlsx bytes using BytesIO and openpyxl engine
    - Handle exceptions gracefully, returning None on failure
    - _Requirements: 6.3_

  - [x] 5.4 Implement `generate_filename` function
    - Generate filename pattern: `[Platform]_[sanitized_base_style_code]_bulk.xlsx`
    - Sanitize base style code: replace spaces and special characters with hyphens
    - _Requirements: 6.2_

  - [ ]* 5.5 Write property test for filename sanitization
    - **Property 7: Filename sanitization follows pattern**
    - **Validates: Requirements 6.2**

- [x] 6. Implement Streamlit UI layer
  - [x] 6.1 Implement `main()` function with platform selector and master form
    - Display platform selector (`st.selectbox`) at the top with options ["Meesho", "Flipkart"], defaulting to "Meesho"
    - Create `st.form` with all input fields: Brand Name, Product Category, Price, GST %, Fabric/Material, Description, Base Style Code, Colors (comma-separated), Sizes (comma-separated)
    - Add "Generate Listing Excel" submit button
    - _Requirements: 1.1, 1.2, 1.4, 2.1, 2.2_

  - [x] 6.2 Wire form submission to generation pipeline
    - On submit: collect form data, run `validate_inputs`, display errors with `st.error` if invalid
    - If valid: call `parse_comma_separated` for colors/sizes, `generate_color_codes`, `generate_variations`, `build_dataframe`
    - Display summary ("Total Variations: N"), preview table via `st.dataframe`
    - Generate Excel bytes and present `st.download_button` with proper filename
    - Handle Excel generation failure: display error message, hide download button
    - _Requirements: 1.3, 5.1, 5.2, 6.1, 6.3, 6.4_

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis
- Unit tests validate specific examples and edge cases
- All code lives in `app.py`; all tests live in `test_app.py`
- The application is launched with `streamlit run app.py`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "2.3"] },
    { "id": 2, "tasks": ["2.2", "2.4", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3"] },
    { "id": 4, "tasks": ["3.4", "3.5", "3.6", "5.1", "5.4"] },
    { "id": 5, "tasks": ["5.2", "5.3", "5.5"] },
    { "id": 6, "tasks": ["6.1"] },
    { "id": 7, "tasks": ["6.2"] }
  ]
}
```
