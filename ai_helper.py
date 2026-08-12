"""
AI Helper Module — Google Gemini Integration for Meesho Bulk Listing Generator
Free tier: 15 RPM, 1M tokens/day
"""

import os
import json
import google.generativeai as genai


def get_gemini_model():
    """Initialize and return Gemini model. Returns None if API key not set."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_api_key_here":
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.0-flash")


def ai_generate_titles(brand, category, colors, occasion, audience, count=1):
    """
    Generate Meesho-compliant SEO product titles using AI.
    Returns dict: {color: title}
    """
    model = get_gemini_model()
    if not model:
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
4. SEO optimized — use trending keywords for the category
5. Format: Brand + Adjective + Color + Category + Feature + Occasion + Audience
6. Each color gets its OWN unique title
7. Do NOT use special characters like _ ( ) in the title

Return ONLY a JSON object like: {{"Black": "title here", "Blue": "title here"}}
No extra text, just the JSON."""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Clean markdown code blocks if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        return json.loads(text)
    except Exception as e:
        print(f"AI Title Error: {e}")
        return None


def ai_generate_description(brand, category, color, fabric, occasion, audience):
    """
    Generate Meesho-compliant product description using AI.
    Returns string description.
    """
    model = get_gemini_model()
    if not model:
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
2. NO claims about quality (best, premium, top quality)
3. Focus on: design, pattern, style, occasion suitability
4. Include care instructions briefly
5. Keep it natural and informative
6. Do NOT mention other platforms

Return ONLY the description text, no quotes or formatting."""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"AI Description Error: {e}")
        return None


def ai_suggest_fields(category, template_fields):
    """
    AI suggests values for template fields based on category.
    Returns dict of {field_name: suggested_value}
    """
    model = get_gemini_model()
    if not model:
        return None

    # Only ask about fields that are relevant
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

    prompt = f"""For a Meesho product listing in category "{category}", suggest the most appropriate values for these fields:

Fields: {json.dumps(fields_to_fill)}

RULES:
1. Only suggest values that Meesho typically accepts
2. For dropdown fields (Fabric, Pattern, Occasion, etc.), use standard Meesho dropdown values
3. For GST %, use 5 for clothing
4. For Country of Origin, use "India"
5. For Net Quantity, use "1" unless it's a pack

Return ONLY a JSON object like: {{"field_name": "value", ...}}
Skip fields you're unsure about. No extra text."""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        return json.loads(text)
    except Exception as e:
        print(f"AI Suggestion Error: {e}")
        return None
