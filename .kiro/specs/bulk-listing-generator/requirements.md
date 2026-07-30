# Requirements Document

## Introduction

A local Python Streamlit web application that generates bulk listing Excel files (.xlsx) for e-commerce platforms Meesho and Flipkart. The application provides a single master input form where sellers enter product details once, selects a target platform, and generates a formatted Excel file with all Color × Size variations using the exact column headers required by the chosen platform.

## Glossary

- **Application**: The Streamlit-based web application for bulk listing generation
- **Platform**: A target e-commerce marketplace (Meesho or Flipkart)
- **Master_Form**: The single input form containing all product fields shared across platforms
- **Base_Style_Code**: A user-provided text identifier for the product line (e.g., TSHIRT-COTTON)
- **Color_Style_Code**: A derived code combining the Base_Style_Code with an abbreviated color identifier (e.g., TSHIRT-COTTON-BLK)
- **SKU**: Stock Keeping Unit — a unique identifier for each Color + Size combination (e.g., TSHIRT-COTTON-BLK-M)
- **Variation**: A single row representing one unique Color + Size combination
- **Listing_File**: The generated .xlsx Excel file containing all variations formatted for the selected platform
- **Platform_Selector**: The UI control allowing the user to choose the target platform

## Requirements

### Requirement 1: Platform Selection

**User Story:** As a seller, I want to select a target platform (Meesho or Flipkart), so that the generated Excel file uses the correct column headers for that marketplace.

#### Acceptance Criteria

1. THE Application SHALL display a Platform_Selector control at the top of the page, above the Master_Form, with exactly two options: "Meesho" and "Flipkart"
2. THE Application SHALL default the Platform_Selector to "Meesho" on page load
3. WHEN the user selects a platform and submits the Master_Form, THE Application SHALL generate the Listing_File and preview table using the column headers corresponding to the selected platform as defined in Requirement 4
4. WHEN the user changes the Platform_Selector value, THE Application SHALL retain the selected platform value until the user changes it again or the page is reloaded

### Requirement 2: Master Form Inputs

**User Story:** As a seller, I want to enter my product details in a single form, so that I can generate bulk listings without re-entering data for each platform.

#### Acceptance Criteria

1. THE Master_Form SHALL contain the following input fields: Brand Name (text, max 100 characters), Product Category (text, max 100 characters), Price (number, accepting values from 1 to 9,999,999 with up to 2 decimal places), GST % (number, accepting values from the set [0, 3, 5, 12, 18, 28]), Fabric / Material (text, max 100 characters), Description (text area, max 2000 characters), Base Style Code (text, max 50 characters), Colors (comma-separated text, max 50 values), and Sizes (comma-separated text, max 50 values)
2. THE Master_Form SHALL contain a "Generate Listing Excel" submit button
3. WHEN the user enters Colors as a comma-separated string, THE Application SHALL treat each comma-separated value as a distinct color after trimming whitespace, ignoring any empty values resulting from consecutive commas or trailing commas
4. WHEN the user enters Sizes as a comma-separated string, THE Application SHALL treat each comma-separated value as a distinct size after trimming whitespace, ignoring any empty values resulting from consecutive commas or trailing commas
5. WHEN the user enters Colors or Sizes containing duplicate values after trimming, THE Application SHALL retain only unique values and discard duplicates

### Requirement 3: Variation Generation Logic

**User Story:** As a seller, I want the application to generate all Color × Size combinations automatically, so that each variation has a unique SKU and style code.

#### Acceptance Criteria

1. WHEN the user submits the Master_Form, THE Application SHALL generate one Variation row for each unique combination of Color and Size from the provided lists, ordered by color first then by size within each color
2. WHEN generating variations, THE Application SHALL assign each color a Color_Style_Code in the format: [Base_Style_Code]-[COLOR_CODE], where COLOR_CODE is the first 3 characters of the color name converted to uppercase (e.g., "Black" → "BLA", "Red" → "RED", "Light Blue" → "LIG")
3. WHEN generating variations, THE Application SHALL assign each Variation a unique SKU in the format: [Color_Style_Code]-[SIZE], where SIZE is the size value converted to uppercase with whitespace trimmed (e.g., "TSHIRT-COTTON-BLA-M", "TSHIRT-COTTON-RED-XL")
4. THE Application SHALL produce exactly (number of unique colors × number of unique sizes) variation rows after deduplication of color and size values
5. IF two or more colors produce the same COLOR_CODE after abbreviation, THEN THE Application SHALL append an incrementing numeric suffix starting from 2 to each duplicate (e.g., "Black" → "BLA", "Blue" → "BLU", "Blanc" → "BLA2")

### Requirement 4: Platform-Specific Column Header Mapping

**User Story:** As a seller, I want the output Excel to use the exact column headers required by the selected platform, so that I can upload directly without manual reformatting.

#### Acceptance Criteria

1. WHEN "Meesho" is the selected platform, THE Application SHALL use the selected_platform variable as the single source of truth and format the Listing_File with these exact column headers in order: ['Style Code', 'SKU ID', 'Product Title', 'Price', 'GST %', 'Fabric', 'Description', 'Color', 'Size']
2. WHEN "Flipkart" is the selected platform, THE Application SHALL format the Listing_File with these exact column headers in order: ['Group ID / Style Code', 'Seller SKU ID', 'Product Name', 'Selling Price', 'GST Rate', 'Material', 'Key Features', 'Color', 'Size']
3. THE Application SHALL map Master_Form fields to platform-specific columns using the following complete mapping — Meesho: Color_Style_Code → 'Style Code', SKU → 'SKU ID', Product Title → 'Product Title', Price → 'Price', GST % → 'GST %', Fabric / Material → 'Fabric', Description → 'Description', Color → 'Color', Size → 'Size'; Flipkart: Color_Style_Code → 'Group ID / Style Code', SKU → 'Seller SKU ID', Product Title → 'Product Name', Price → 'Selling Price', GST % → 'GST Rate', Fabric / Material → 'Material', Description → 'Key Features', Color → 'Color', Size → 'Size'
4. WHEN generating the Product Title value for each Variation row, THE Application SHALL construct it by concatenating: [Brand Name] [Product Category] - [Color] - [Size] (e.g., "BrandX Cotton T-Shirt - Black - M")
5. THE Application SHALL populate the 'Style Code' (Meesho) or 'Group ID / Style Code' (Flipkart) column with the Color_Style_Code value, so that all size variations of the same color share the same style code

### Requirement 5: Output Preview and Summary

**User Story:** As a seller, I want to see a summary and preview of generated variations before downloading, so that I can verify the data is correct.

#### Acceptance Criteria

1. WHEN variations are generated, THE Application SHALL display a summary showing the text "Total Variations:" followed by the numeric count of variations produced (equal to number of colors × number of sizes)
2. WHEN variations are generated, THE Application SHALL display a preview table containing all generated variation rows with the platform-specific column headers as defined in Requirement 4, where the displayed data matches the content of the downloadable Listing_File exactly

### Requirement 6: Excel File Download

**User Story:** As a seller, I want to download the generated listing as an .xlsx file, so that I can upload it to the marketplace.

#### Acceptance Criteria

1. WHEN variations are generated, THE Application SHALL display a download button for the Listing_File in .xlsx format that was not visible prior to generation
2. THE Application SHALL name the Listing_File using the pattern: [Platform]_[Base_Style_Code]_bulk.xlsx (e.g., Meesho_TSHIRT-COTTON_bulk.xlsx), replacing any spaces or special characters in Base_Style_Code with hyphens
3. THE Application SHALL generate the .xlsx file using the openpyxl engine via Pandas, containing exactly the variation rows and platform-specific column headers produced during generation
4. WHEN the .xlsx file generation succeeds, THE Application SHALL present the download button to the user
5. IF the .xlsx file generation fails, THEN THE Application SHALL display an error message indicating that file generation was unsuccessful and the download button SHALL not be presented

### Requirement 7: Project Portability and Setup

**User Story:** As a developer, I want the project to be self-contained with clear setup instructions, so that it can run on any local machine with Python installed.

#### Acceptance Criteria

1. THE Application SHALL have its source code contained in a single file named "app.py"
2. THE Application SHALL include a "requirements.txt" file listing all dependencies: streamlit, pandas, openpyxl
3. THE Application SHALL be launchable via the terminal command: `streamlit run app.py`
4. THE Application SHALL require Python 3.8 or higher as a minimum runtime version
5. WHEN a developer runs `pip install -r requirements.txt` followed by `streamlit run app.py` in the project directory, THE Application SHALL start without import errors or missing-dependency failures

### Requirement 8: Input Validation

**User Story:** As a seller, I want the application to validate my inputs, so that I do not generate malformed listings.

#### Acceptance Criteria

1. IF the user submits the Master_Form with any required text field (Brand Name, Product Category, Fabric / Material, Description, Base Style Code) containing only whitespace or left blank, THEN THE Application SHALL display an error message indicating which fields are missing and SHALL NOT generate the Listing_File
2. IF the user submits the Master_Form with Price as a non-positive number or a non-numeric value, THEN THE Application SHALL display an error message indicating the Price must be a positive number and SHALL NOT generate the Listing_File
3. IF the user submits the Master_Form with Colors or Sizes as a blank value, whitespace-only, or containing no valid entries after trimming whitespace and splitting by comma, THEN THE Application SHALL display an error message indicating that at least one color and one size are required and SHALL NOT generate the Listing_File
4. IF the user submits the Master_Form with GST % as a negative number or a non-numeric value, THEN THE Application SHALL display an error message indicating that GST % must be a number equal to or greater than 0 and SHALL NOT generate the Listing_File
