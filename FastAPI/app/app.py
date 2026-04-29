from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import easyocr
import numpy as np
import cv2
import pandas as pd
import re

app = FastAPI()

import os
frontend_path = os.path.join(os.path.dirname(__file__), "../../frontend")
app.mount("/static", StaticFiles(directory=frontend_path, html=True), name="frontend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================== LOAD DATA ==================
reader = easyocr.Reader(['en'], gpu=False)

data_dir = os.path.join(os.path.dirname(__file__), "data")
ingredients_df = pd.read_csv(os.path.join(data_dir, "ingredients.csv"))
products_df = pd.read_csv(os.path.join(data_dir, "products.csv"))
home_remedies_df = pd.read_csv(os.path.join(data_dir, "home_remedies.csv"))
food_df = pd.read_csv(os.path.join(data_dir, "food.csv"))

ingredients_df['name'] = ingredients_df['name'].str.strip().str.lower()

# ================== SMART PRODUCT MAP ==================
PRODUCT_MAP = {
    "mascara": ["mascara", "lash", "eyelash"],
    "shampoo": ["shampoo", "hair wash", "anti-dandruff", "anti dandruff"],
    "facewash": ["face", "cleanser", "wash", "soap", "face wash"],
    "beverage": ["drink", "soda", "cola", "juice", "beverage", "soft drink"],
    "oil": ["oil", "hair oil", "onion oil"],
    "sunscreen": ["sunscreen", "spf", "sun block", "uv protection", "sun screen"],
    "cream": ["cream", "moisturizer", "moisturising", "lotion"],
    "serum": ["serum", "vitamin c", "niacinamide serum", "brightening"],
}

# For eye products, skip home remedies
EYE_PRODUCT_KEYWORDS = ["mascara", "eyeliner", "eye liner", "kajal", "kohl"]

def detect_product_type(text: str) -> str | None:
    text = text.lower()
    for ptype, keywords in PRODUCT_TYPE_MAP.items():
        if any(k in text for k in keywords):
            return ptype
    return None

NO_REMEDY_PRODUCTS = ["mascara", "eyeliner", "eye liner", "kajal", "eye shadow", "eyeshadow"]

def is_eye_product(text):
    text = text.lower()
    return any(k in text for k in EYE_PRODUCT_KEYWORDS)


# ================== IMAGE PREPROCESSING ==================
def preprocess_image(image: np.ndarray) -> np.ndarray:
    """Enhance image quality for better OCR results."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Upscale small images
    h, w = gray.shape
    if w < 1000:
        scale = 1000 / w
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # CLAHE contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Mild sharpening
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    enhanced = cv2.filter2D(enhanced, -1, kernel)

    return enhanced


# ================== INGREDIENT EXTRACTION ==================
def extract_ingredients_text(full_text: str) -> str:
    """Try several patterns to isolate the ingredients section."""

    patterns = [
        r'ingredient[s]?\s*[:\-]?\s*(.*?)(?:usage|direction|how to use|warning|apply|expiry|mfg|net wt|$)',
        r'contains?\s*[:\-]?\s*(.*?)(?:usage|direction|warning|$)',
        r'composition\s*[:\-]?\s*(.*?)(?:usage|direction|warning|$)',
        r'ingr\s*[:\-]?\s*(.*?)(?:usage|direction|warning|$)',
    ]

    for pattern in patterns:
        match = re.search(pattern, full_text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()

    # Fallback: find comma-dense segments (ingredient lists have many commas)
    sentences = re.split(r'[\.\n]', full_text)
    comma_rich = [s.strip() for s in sentences if s.count(',') >= 2]
    if comma_rich:
        return ' '.join(comma_rich)

    return full_text


# ================== SCAN ENDPOINT ==================
@app.post("/purescan")
async def scan(
    file: UploadFile = File(...),
    min_budget: int = Form(0),
    max_budget: int = Form(999999)
):
    contents = await file.read()
    np_arr = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if image is None:
        return {"error": "Invalid image. Please upload a clear product photo."}

    # Preprocess for better OCR
    enhanced = preprocess_image(image)

    # Run OCR
    result = reader.readtext(enhanced)
    full_text = " ".join([r[1] for r in result])
    full_text_lower = full_text.lower()

    # Extract ingredients section
    ingredients_raw = extract_ingredients_text(full_text_lower)
    ingredients_raw = re.sub(r'[^a-zA-Z0-9\s,.\-()]', ' ', ingredients_raw)
    ingredients_raw = re.sub(r'\s+', ' ', ingredients_raw).strip()

    ingredients_text = re.sub(r'[^a-zA-Z0-9\s,.-]', ' ', ingredients_text)
    ingredients_text = re.sub(r'\s+', ' ', ingredients_text).strip()

    ingredients_output = []
    harmful = []
    seen_known = set()

    # 1. Find all KNOWN ingredients directly from the full text
    for _, row in ingredients_df.iterrows():
        ing = str(row['name']).lower().strip()
        if len(ing) < 2: continue
        
        # Word boundary match to ensure accuracy
        if re.search(rf'\b{re.escape(ing)}\b', ingredients_text):
            risk = str(row.get("risk_level", "Unknown"))
            ingredients_output.append({
                "name": ing.title(),
                "decoded": row.get("simple_name", "Unknown"),
                "risk": risk,
                "description": row.get("side_effects", "No description")
            })
            seen_known.add(ing)
            if risk.lower() in ["medium", "high"]:
                harmful.append(ing)

    # 2. Try to find UNKNOWN ingredients (if comma separated)
    parts = [p.strip() for p in ingredients_text.split(",") if len(p.strip()) > 2]
    for part in parts:
        part_lower = part.lower()
        # Skip if it's a huge unseparated chunk or already contains a known ingredient
        if len(part_lower) > 40:
            continue
        if any(k in part_lower for k in seen_known):
            continue
            
        ingredients_output.append({
            "name": part.title(),
            "decoded": "Unknown",
            "risk": "Unknown",
            "description": "Not in database"
        })

    # ================== DETECT PRODUCT TYPE ==================
    product_type = detect_product_type(full_text_lower)

    # ================== PRODUCT SUGGESTIONS ==================
    product_suggestions = []

    for _, p in products_df.iterrows():
        try:
            price = int(float(str(p.get("price", 0)).replace("₹", "").strip()))
        except (ValueError, TypeError):
            price = 0

        if not (min_budget <= price <= max_budget):
            continue

        category = str(p.get("category", "")).strip().lower()
        name_col = str(p.get("name", "")).strip().lower()

        if product_type:
            # Match if product_type keyword appears in category or name
            if product_type in category or product_type in name_col:
                product_suggestions.append({
                    "name": p.get("name", "N/A"),
                    "price": price,
                    "description": str(p.get("description", "")),
                    "category": p.get("category", "N/A"),
                    "rating": p.get("rating", "N/A"),
                    "review_source": p.get("review_source", "N/A"),
                    "safety_note": p.get("safety_note", "N/A"),
                })
        else:
            product_suggestions.append({
                "name": p.get("name", "N/A"),
                "price": price,
                "description": str(p.get("description", "")),
                "category": p.get("category", "N/A"),
                "rating": p.get("rating", "N/A"),
                "review_source": p.get("review_source", "N/A"),
                "safety_note": p.get("safety_note", "N/A"),
            })

    # ================== FOOD ALTERNATIVES ==================
    # Show food alternatives when product type is beverage/food or unknown
    food_alternatives = []

    if product_type in ("beverage", "food", None):
        for _, f in food_df.iterrows():
            try:
                price = int(float(str(f.get("price", 0)).strip()))
            except (ValueError, TypeError):
                price = 0

            if not (min_budget <= price <= max_budget):
                continue

            # Match via trigger_keywords column OR name/description
            trigger_kw = str(f.get("trigger_keywords", "")).lower()
            f_name = str(f.get("name", "")).lower()
            f_desc = str(f.get("description", "")).lower()
            combined = trigger_kw + " " + f_name + " " + f_desc

            # STRICT MATCH — only show products of detected type
            if product_type:
                if product_type in category or product_type in name:
                    product_suggestions.append({
                        "name": p['name'],
                        "price": price,
                        "description": p.get("description", ""),
                        "category": p.get("category"),
                        "rating": p.get("rating", "N/A"),
                        "review_source": p.get("review_source", "N/A"),
                        "safety_note": p.get("safety_note", "N/A")
                    })
            else:
                product_suggestions.append({
                    "name": p['name'],
                    "price": price,
                    "description": p.get("description", ""),
                    "category": p.get("category"),
                    "rating": p.get("rating", "N/A"),
                    "review_source": p.get("review_source", "N/A"),
                    "safety_note": p.get("safety_note", "N/A")
                })

        except (ValueError, TypeError):
            continue

    # ================== REMEDIES ==================
    home_remedies = []

    # BLOCK for mascara/eyeliner/kajal — NO home remedies for eye products
    if not is_eye_product(full_text):
        for _, r in home_remedies_df.iterrows():
            # Match remedy to product type if detected
            if product_type and product_type not in str(r.get("category", "")).lower() and product_type not in str(r.get("tags", "")).lower():
                continue
            
            home_remedies.append({
                "remedy": r.get("remedy_name", ""),
                "issue": r.get("issue", ""),
                "description": r.get("description", "")
            })

    # ================== FOOD ALTERNATIVES ==================
    food_alternatives = []

    if product_type == "beverage" or "food" in (product_type or ""):
        for _, f in food_df.iterrows():
            try:
                price = int(f.get("price", 0))
                if min_budget <= price <= max_budget:
                    food_alternatives.append({
                        "name": f.get("name", "N/A"),
                        "alternative": f.get("healthy_alternative", "N/A"),
                        "description": f.get("description", "N/A"),
                        "price": price
                    })
            except (ValueError, TypeError):
                continue

    # ================== BUILD REPLY ==================
    risk_count = len(harmful)
    total_count = len(ingredients_output)

    if risk_count == 0 and total_count > 0:
        reply = f"✅ Scan Complete — {total_count} ingredients found. No high-risk ingredients detected!"
    elif risk_count > 0:
        reply = f"⚠️ Scan Complete — {total_count} ingredients found, {risk_count} flagged as risky."
    elif total_count == 0:
        reply = "📸 Scan Complete — No ingredients could be identified. Try a clearer image."
    else:
        reply = "✅ Scan Complete"

    return {
        "reply": reply,
        "extracted_text": ingredients_text,
        "ingredients": ingredients_output,
        "product_suggestions": product_suggestions[:5],
        "food_alternatives": food_alternatives[:5],
        "home_remedies": home_remedies[:5],
        "food_alternatives": food_alternatives[:5]
    }


# ============================================ CHAT ======================
@app.post("/chat")
async def chat(request: dict):
    user_message = str(request.get("message", "")).strip().lower()
    min_budget = int(float(str(request.get("min_budget", 0))))
    max_budget = int(float(str(request.get("max_budget", 999999))))

    user_message = (request.get("message") or "").lower()
    min_budget = int(request.get("min_budget", 0))
    max_budget = int(request.get("max_budget", 999999))

    stop_words = {"i", "want", "need", "a", "an", "the", "good", "best", "some", "for", "to", "my", "is", "of", "and", "in", "with", "can", "you", "show", "me", "any", "are", "have", "give", "suggest", "tell", "about"}
    message_words = {w for w in set(user_message.split()) if w not in stop_words and len(w) > 2}

    product_results = []
    food_results = []
    remedy_results = []

    # ================= DETECT FOOD =================
    food_keywords = {
        "food", "eat", "drink", "snack", "chips", "coconut",
        "juice", "makhana", "chana", "oats", "diet", "healthy",
        "breakfast", "lunch", "dinner", "meal"
    }

    is_food_query = any(word in user_message for word in food_keywords)

    # ================= FOOD SEARCH =================
    if is_food_query:

        for _, food_item in food_df.iterrows():

            food_name = str(food_item.get("name", "")).lower()
            food_desc = str(food_item.get("description", "")).lower()
            food_alt = str(food_item.get("healthy_alternative", "")).lower()
            food_triggers = str(food_item.get("trigger_keywords", "")).lower().replace("|", " ")

            combined_text = food_name + " " + food_desc + " " + food_alt + " " + food_triggers

            if any(word in re.findall(r'\w+', combined_text) for word in message_words):

                try:
                    price = int(food_item.get("price", 0))
                except (ValueError, TypeError):
                    price = 0

                if min_budget <= price <= max_budget:

                    food_results.append({
                        "name": food_item.get("name", "N/A"),
                        "healthy_alternative": food_item.get("healthy_alternative", "N/A"),
                        "description": food_item.get("description", "N/A"),
                        "price": price
                    })

    # ================= PRODUCT SEARCH =================
    else:

        for _, product in products_df.iterrows():

            product_name = str(product.get("name", "")).lower()
            product_category = str(product.get("category", "")).lower()
            product_desc = str(product.get("description", "")).lower()

            combined_text = product_name + " " + product_category + " " + product_desc

            if any(word in re.findall(r'\w+', combined_text) for word in message_words):

                try:
                    price = int(product.get("price", 0))
                except (ValueError, TypeError):
                    price = 0

                if min_budget <= price <= max_budget:

                    product_results.append({
                        "name": product.get("name", "N/A"),
                        "price": price,
                        "description": product.get("description", "N/A"),
                        "category": product.get("category", "N/A"),
                        "rating": product.get("rating", "N/A"),
                        "review_source": product.get("review_source", "N/A"),
                        "safety_note": product.get("safety_note", "N/A")
                    })

    # ================= HOME REMEDIES (WITH EYE PRODUCT FILTER) =================
    seen_remedies = set()

    # Block eye-product remedies in chat too
    eye_blocked = is_eye_product(user_message)

    for _, remedy in home_remedies_df.iterrows():

        issue = str(remedy.get("issue", "")).lower()
        remedy_name = str(remedy.get("remedy_name", "")).lower()
        description = str(remedy.get("description", "")).lower()
        category = str(remedy.get("category", "")).lower()

        # Skip eye-related remedies if user asked about eye products
        if eye_blocked and category in ["eye", "eyes"]:
            continue

        combined_text = issue + " " + remedy_name + " " + description

        if any(word in re.findall(r'\w+', combined_text) for word in message_words):

            key = remedy.get("remedy_name", "N/A")

            if key in seen_remedies:
                continue

            seen_remedies.add(key)

            remedy_results.append({
                "issue": remedy.get("issue", "N/A"),
                "remedy": remedy.get("remedy_name", "N/A"),
                "description": remedy.get("description", "N/A")
            })

    # ================= FINAL RESPONSE =================
    if not product_results and not food_results and not remedy_results:
        return {
            "reply": "❌ No results found. Try keywords like shampoo, face wash, coconut water, chips, dandruff, acne, etc.",
            "products": [],
            "food_suggestions": [],
            "home_remedies": [],
        }

    # ── Stop words ──
    stop_words = {
        "i", "want", "need", "a", "an", "the", "good", "best", "some",
        "for", "to", "my", "is", "of", "and", "in", "with", "can", "you",
        "show", "me", "any", "are", "have", "do", "suggest", "recommendation",
        "give", "please", "real", "natural", "healthy", "organic", "get"
    }

    # Extract meaningful words (length > 2, not stop-words)
    message_words = [
        w for w in re.findall(r'\w+', user_message)
        if w not in stop_words and len(w) > 2
    ]

    # ── Food keywords (checked as substrings, not word splits) ──
    FOOD_KEYWORDS = [
        "food", "eat", "drink", "snack", "chips", "coconut water",
        "juice", "makhana", "chana", "oats", "diet", "healthy snack",
        "biscuit", "cookie", "chocolate", "bread", "breakfast", "lunch",
        "dinner", "meal", "beverage", "energy drink",
    ]

    is_food_query = any(kw in user_message for kw in FOOD_KEYWORDS)

    product_results  = []
    food_results     = []
    remedy_results   = []

    # ================== FOOD SEARCH ==================
    if is_food_query:
        for _, f in food_df.iterrows():
            f_name    = str(f.get("name", "")).lower()
            f_desc    = str(f.get("description", "")).lower()
            f_alt     = str(f.get("healthy_alternative", "")).lower()
            f_trigger = str(f.get("trigger_keywords", "")).lower()
            combined  = f_name + " " + f_desc + " " + f_alt + " " + f_trigger

            # Match if any meaningful word OR full keyword appears
            word_match = any(w in combined for w in message_words)
            kw_match   = any(kw in combined for kw in FOOD_KEYWORDS if kw in user_message)

            if word_match or kw_match:
                try:
                    price = int(float(str(f.get("price", 0))))
                except (ValueError, TypeError):
                    price = 0

                if min_budget <= price <= max_budget:
                    food_results.append({
                        "name": f.get("name", "N/A"),
                        "healthy_alternative": f.get("healthy_alternative", "N/A"),
                        "description": f.get("description", "N/A"),
                        "price": price,
                    })

    # ================== PRODUCT SEARCH ==================
    else:
        for _, p in products_df.iterrows():
            p_name     = str(p.get("name", "")).lower()
            p_category = str(p.get("category", "")).lower()
            p_desc     = str(p.get("description", "")).lower()
            p_use_case = str(p.get("use_case", "")).lower()
            combined   = p_name + " " + p_category + " " + p_desc + " " + p_use_case

            if any(w in combined for w in message_words):
                try:
                    price = int(float(str(p.get("price", 0))))
                except (ValueError, TypeError):
                    price = 0

                if min_budget <= price <= max_budget:
                    product_results.append({
                        "name": p.get("name", "N/A"),
                        "price": price,
                        "description": str(p.get("description", "N/A")),
                        "category": str(p.get("category", "N/A")),
                        "rating": p.get("rating", "N/A"),
                        "review_source": p.get("review_source", "N/A"),
                    })

    # ================== HOME REMEDIES SEARCH ==================
    seen_remedies = set()

    for _, r in remedies_df.iterrows():
        issue       = str(r.get("issue", "")).lower()
        remedy_name = str(r.get("remedy_name", "")).lower()
        description = str(r.get("description", "")).lower()
        tags        = str(r.get("tags", "")).lower()
        combined    = issue + " " + remedy_name + " " + description + " " + tags

        if any(w in combined for w in message_words):
            key = r.get("remedy_name", "")
            if key in seen_remedies:
                continue
            seen_remedies.add(key)
            remedy_results.append({
                "issue": r.get("issue", "N/A"),
                "remedy": r.get("remedy_name", "N/A"),
                "description": r.get("description", "N/A"),
                "how_to_use": r.get("how_to_use", ""),
            })

    # ================== RESPONSE ==================
    has_results = product_results or food_results or remedy_results

    if not has_results:
        return {
            "reply": "❌ No results found. Try keywords like shampoo, face wash, juice, chips, coconut water, etc.",
            "products": [],
            "food_suggestions": [],
            "home_remedies": [],
        }

    # Build a smart reply message
    parts = []
    if product_results:
        parts.append(f"{len(product_results[:5])} product(s)")
    if food_results:
        parts.append(f"{len(food_results[:5])} food option(s)")
    if remedy_results:
        parts.append(f"{len(remedy_results[:5])} home remedy(ies)")

    reply = f"Found {', '.join(parts)} for you 😊"

    if eye_blocked:
        reply += "\n⚠️ Home remedies are not recommended for eye products."

    return {
        "reply": reply,
        "products": product_results[:5],
        "food_suggestions": food_results[:5],
        "home_remedies": remedy_results[:5],
    }
