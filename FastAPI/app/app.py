from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import easyocr
import numpy as np
import cv2
import pandas as pd
import re

app = FastAPI()

app.mount("/static", StaticFiles(directory="../../frontend", html=True), name="frontend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================== LOAD DATA ==================
reader = easyocr.Reader(['en'], gpu=False)

ingredients_df = pd.read_csv("data/ingredients.csv").dropna(how="all")
products_df    = pd.read_csv("data/products.csv").dropna(how="all")
remedies_df    = pd.read_csv("data/home_remedies.csv").dropna(how="all")
food_df        = pd.read_csv("data/food.csv").dropna(how="all")

ingredients_df['name'] = ingredients_df['name'].str.strip().str.lower()

# ================== PRODUCT TYPE MAP ==================
# Maps internal product_type key -> keywords to search in OCR text
PRODUCT_TYPE_MAP = {
    "mascara":   ["mascara", "lash", "eyelash"],
    "shampoo":   ["shampoo", "hair wash"],
    "facewash":  ["face wash", "face cleanser", "cleanser", "soap"],
    "oil":       ["hair oil", "onion oil", "coconut oil"],
    "sunscreen": ["sunscreen", "spf", "sun protect"],
    "serum":     ["serum", "vitamin c", "niacinamide"],
    "cream":     ["moisturizer", "moisturising", "cream", "lotion"],
    "beverage":  ["juice", "drink", "soda", "cola", "energy drink", "beverage", "coconut water"],
    "food":      ["chips", "snack", "biscuit", "cookie", "chocolate", "bread", "oats", "makhana", "chana"],
}

# For eye products, skip home remedies
EYE_PRODUCT_KEYWORDS = ["mascara", "eyeliner", "eye liner", "kajal", "kohl"]

def detect_product_type(text: str) -> str | None:
    text = text.lower()
    for ptype, keywords in PRODUCT_TYPE_MAP.items():
        if any(k in text for k in keywords):
            return ptype
    return None

def is_eye_product(text: str) -> bool:
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

    # Parse individual ingredients
    parts = [p.strip() for p in ingredients_raw.split(",") if len(p.strip()) > 1]

    ingredients_output = []
    harmful = []
    seen_names = set()

    for part in parts:
        part_lower = part.lower()
        matched = False

        for _, row in ingredients_df.iterrows():
            ing_name = str(row['name']).strip()
            if ing_name and ing_name in part_lower:
                if ing_name in seen_names:
                    matched = True
                    break
                seen_names.add(ing_name)
                risk = str(row.get("risk_level", "Unknown")).strip()
                ingredients_output.append({
                    "name": ing_name.title(),
                    "decoded": str(row.get("simple_name", "N/A")),
                    "risk": risk,
                    "description": str(row.get("side_effects", "N/A"))
                })
                if risk.lower() in ["medium", "high"]:
                    harmful.append(ing_name)
                matched = True
                break

        if not matched:
            clean_name = part.strip().title()
            if clean_name and clean_name not in seen_names:
                seen_names.add(clean_name)
                ingredients_output.append({
                    "name": clean_name,
                    "decoded": "Not in database",
                    "risk": "Unknown",
                    "description": "No information available"
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

            # Check if any word from OCR text matches food item
            ocr_words = set(re.findall(r'\w{3,}', full_text_lower))
            if any(w in combined for w in ocr_words) or product_type in ("beverage", "food"):
                food_alternatives.append({
                    "name": f.get("name", "N/A"),
                    "healthy_alternative": f.get("healthy_alternative", "N/A"),
                    "description": f.get("description", "N/A"),
                    "price": price,
                })

    # ================== HOME REMEDIES ==================
    home_remedies = []

    if not is_eye_product(full_text_lower):
        for _, r in remedies_df.iterrows():
            cat   = str(r.get("category", "")).strip().lower()
            tags  = str(r.get("tags", "")).strip().lower()
            rtype = str(r.get("final_product_type", "")).strip().lower()

            if product_type:
                if product_type not in cat and product_type not in tags and product_type not in rtype:
                    continue

            home_remedies.append({
                "remedy": r.get("remedy_name", "N/A"),
                "issue": r.get("issue", "N/A"),
                "description": r.get("description", "N/A"),
                "how_to_use": r.get("how_to_use", ""),
            })

    return {
        "extracted_text": ingredients_raw,
        "product_type_detected": product_type or "general",
        "ingredients": ingredients_output,
        "product_suggestions": product_suggestions[:5],
        "food_alternatives": food_alternatives[:5],
        "home_remedies": home_remedies[:5],
    }


# ================== CHAT ENDPOINT ==================
@app.post("/chat")
async def chat(request: dict):
    user_message = str(request.get("message", "")).strip().lower()
    min_budget = int(float(str(request.get("min_budget", 0))))
    max_budget = int(float(str(request.get("max_budget", 999999))))

    if not user_message:
        return {
            "reply": "Please type something to search.",
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

    return {
        "reply": "Here are your results 😊",
        "products": product_results[:5],
        "food_suggestions": food_results[:5],
        "home_remedies": remedy_results[:5],
    }
