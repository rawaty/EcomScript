"""
AI Helper Module — Google Gemini Integration
Uses new google-genai library with gemini-3-flash-preview model.
"""

import os
import json

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

MODEL_NAME = "gemini-3-flash-preview"


def get_client():
    """Get Gemini client. Returns None if not configured."""
    if not GENAI_AVAILABLE:
        return None
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_gemini_key_here":
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception:
        return None


def ai_generate_titles(brand, category, colors, occasion, audience, count=1):
    """Generate Meesho-compliant SEO product titles. Returns dict: {color: title}"""
    client = get_client()
    if not client:
        return None

    prompt = f"""Generate {len(colors)} unique Meesho-compliant product titles.

Brand: {brand}
Category: {category}
Colors: {', '.join(colors)}
Occasion: {occasion}
Target Audience: {audience}

STRICT RULES:
1. NO restricted keywords: comfort, comfortable, EVA, everyday, daily wear, elegant, best quality, premium quality, high quality, Amazon, Flipkart, Myntra, Ajio
2. Include the color name naturally in each title
3. Max 80 characters per title
4. SEO optimized
5. Format: Brand + Adjective + Color + Category + Feature + Occasion + Audience
6. Each color gets its OWN unique title
7. Do NOT use special characters like _ ( ) in the title

Return ONLY a JSON object like: {{"Black": "title here", "Blue": "title here"}}
No extra text, just the JSON."""

    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0].strip()
        return json.loads(text)
    except Exception as e:
        print(f"AI Title Error: {e}")
        return None


def ai_generate_description(brand, category, color, fabric, occasion, audience):
    """Generate Meesho-compliant product description."""
    client = get_client()
    if not client:
        return None

    prompt = f"""Write a Meesho product description (3-4 lines, max 200 words).

Brand: {brand}
Category: {category}
Color: {color}
Fabric: {fabric}
Occasion: {occasion}
Audience: {audience}

STRICT RULES:
1. NO restricted keywords: comfort, comfortable, EVA, everyday, daily wear, elegant, best quality, premium quality, high quality, Amazon, Flipkart, Myntra, Ajio
2. Focus on: design, pattern, style, occasion suitability
3. Keep it natural and informative
4. Do NOT mention other platforms

Return ONLY the description text, no quotes or formatting."""

    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        return response.text.strip()
    except Exception as e:
        print(f"AI Description Error: {e}")
        return None


def ai_suggest_fields(category, template_fields):
    """AI suggests values for template fields based on category."""
    client = get_client()
    if not client:
        return None

    fields_to_fill = [f for f in template_fields if f not in (
        'Product Name', 'SKU ID', 'Product ID / Style ID', 'Brand Name',
        'Group ID', 'Image 1 (Front)', 'Image 2', 'Image 3', 'Image 4',
        'Variation', 'Meesho Price', 'Wrong/Defective Returns Price', 'MRP',
        'ERROR STATUS', 'ERROR MESSAGE', 'Inventory', 'Color',
        'Manufacturer Name', 'Manufacturer Address', 'Manufacturer Pincode',
        'Packer Name', 'Packer Address', 'Packer Pincode',
        'Importer Name', 'Importer Address', 'Importer Pincode',
    )]
    if not fields_to_fill:
        return None

    prompt = f"""For a Meesho product in category "{category}", suggest values for:

Fields: {json.dumps(fields_to_fill)}

RULES:
1. Use standard Meesho dropdown values
2. GST % = 5 for clothing
3. Country of Origin = India
4. Net Quantity = 1

Return ONLY JSON: {{"field_name": "value", ...}}
Skip uncertain fields."""

    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0].strip()
        return json.loads(text)
    except Exception as e:
        print(f"AI Suggestion Error: {e}")
        return None


def ai_analyze_image(image_bytes, category_hint="", valid_options=None):
    """
    Analyze product image and return detected attributes.
    valid_options: dict of {field_name: [valid_values]} from template dropdowns.
    Returns dict: {color, fabric, pattern, category, title_suggestion, description}
    """
    client = get_client()
    if not client:
        return None

    # Build validation constraints for prompt
    constraints = ""
    if valid_options:
        constraints = "\n\nIMPORTANT — You MUST pick values ONLY from these valid dropdown options:\n"
        for field, values in valid_options.items():
            constraints += f"- {field}: {', '.join(values[:20])}\n"
        constraints += "\nIf a detected value doesn't match any option, pick the CLOSEST match from the list."

    prompt = f"""Analyze this product image for a Meesho listing.
{f'Category hint: {category_hint}' if category_hint else ''}
{constraints}

Detect and return:
- color: Main color of the product (MUST be from Color dropdown if provided)
- fabric: Material/fabric type (MUST be from Fabric dropdown if provided)
- pattern: Pattern type (MUST be from Pattern dropdown if provided)
- category: Product category (Kurtis & Kurtas, Flip Flops, etc.)
- occasion: Suitable occasion (MUST be from Occasion dropdown if provided)
- title_suggestion: A Meesho-compliant product title (no restricted keywords like comfort, elegant, EVA, daily wear, Amazon, Flipkart)
- description: 2-3 line product description (no restricted keywords)

Return ONLY valid JSON, no extra text."""

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}},
                prompt
            ]
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0].strip()
        return json.loads(text)
    except Exception as e:
        print(f"AI Image Analysis Error: {e}")
        return None
