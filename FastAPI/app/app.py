from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
import easyocr
import numpy as np
import cv2
import pandas as pd
import re
from difflib import get_close_matches
import os

app = FastAPI(docs_url="/docs", openapi_url="/openapi.json")

# ================== PATHS & STATIC ==================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "../../frontend")
DATA_DIR = os.path.join(BASE_DIR, "data")

# Mount static files safely
app.mount("/static", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

# ================== CORS ==================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================== ROOT REDIRECT ==================
@app.get("/")
async def root():
    return RedirectResponse(url="/static/purescan.html")

# ================== LOAD DATABASES ==================
reader = easyocr.Reader(['en'], gpu=False)

def safe_load_csv(filename):
    """Safely loads CSV and replaces NaN values with empty strings to prevent JSON crashes."""
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        return pd.read_csv(path).fillna("")
    return pd.DataFrame()

ingredients_df = safe_load_csv("ingredients.csv")
if not ingredients_df.empty and 'name' in ingredients_df.columns:
    ingredients_df['name'] = ingredients_df['name'].astype(str).str.lower()

products_df = safe_load_csv("products.csv")
home_remedies_df = safe_load_csv("home_remedies.csv")
food_df = safe_load_csv("food.csv") # FIXED: Added missing food_df!

# ================== CLEANING ==================
CORRECTIONS = {
    "befaine": "betaine",
    "walet": "water",
    "olficinale": "officinale",
    "oflicinalis": "officinalis",
    "propvl": "propyl",
    "krimonium": "trimonium",
    "purified water": "water",
}

def clean_text(text):
    text = str(text).lower()
    for wrong, correct in CORRECTIONS.items():
        text = text.replace(wrong, correct)
    return text

def split_ingredients(text):
    """Safely splits ingredients based on punctuation instead of spaces, preserving multi-word ingredients."""
    raw_parts = re.split(r'[,.\n|]', text)
    final_parts = []

    for part in raw_parts:
        part = part.strip()
        part = re.sub(r'[^a-z0-9\s-]', '', part) # Remove weird OCR characters
        if len(part) > 1: # Allow small ingredients like "wax", "tin", "oat"
            final_parts.append(part)

    return final_parts

# ================== MATCHING ==================
def match_ingredient(part):
    if ingredients_df.empty:
        return None
        
    part = part.lower().strip()

    # 1. EXACT MATCH
    exact = ingredients_df[ingredients_df['name'] == part]
    if not exact.empty:
        return exact.iloc[0]

    # 2. PARTIAL MATCH (Safe Check)
    for _, row in ingredients_df.iterrows():
        name = str(row.get('name', ''))
        # Ensure DB name is substantial (>3 chars) and perfectly exists in the string
        if len(name) > 3 and name in part:
            return row

    # 3. FUZZY MATCH (Typo tolerance)
    possibilities = ingredients_df['name'].tolist()
    fuzzy_matches = get_close_matches(part, possibilities, n=1, cutoff=0.7)
    if fuzzy_matches:
        return ingredients_df[ingredients_df['name'] == fuzzy_matches[0]].iloc[0]

    return None

# ================== PRODUCT TYPES ==================
def detect_product_type(text):
    text = text.lower()
    if any(x in text for x in ["sodium lauroyl", "cocamidopropyl", "betaine", "dimethiconol", "guar hydroxy", "piroctone"]):
        return "shampoo"
    if any(x in text for x in ["ci 77499", "ci 77266", "wax", "carnauba", "cera alba"]):
        return "mascara"
    if any(x in text for x in ["salicylic acid", "cleanser", "face wash"]):
        return "facewash"
    return "unknown"

def is_eye_product(text):
    return any(x in text for x in ["mascara", "eyeliner", "kajal", "eye"])

# ================== SCAN ENDPOINT ==================
@app.post("/purescan")
async def scan(file: UploadFile = File(...), min_budget: int = Form(100), max_budget: int = Form(2000)):
    contents = await file.read()
    image = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(image, cv2.IMREAD_COLOR)

    if image is None:
        return JSONResponse(status_code=400, content={"error": "Invalid image format"})

    # 1. OCR
    result = reader.readtext(image)
    full_text = " ".join([str(r[1]) for r in result]).lower()

    # 2. Extract strictly the ingredients part
    regex_match = re.search(
        r'ingredient[s]?\s*[:\-]?\s*(.*?)(usage|direction|warning|apply|manufactured|made in|$)',
        full_text,
        re.IGNORECASE | re.DOTALL
    )
    ingredients_text = regex_match.group(1) if regex_match else full_text

    # 3. Clean & Split
    ingredients_text = clean_text(ingredients_text)
    parts = split_ingredients(ingredients_text)

    ingredients_output = []
    harmful = []
    seen = set()

    # 4. Ingredient Analysis
    for part in parts:
        matched_row = match_ingredient(part)

        if matched_row is not None:
            name = str(matched_row.get('name', part)).title()

            if name.lower() in seen:
                continue
            seen.add(name.lower())

            risk = str(matched_row.get("risk_level", "Unknown")).title()
            
            ingredients_output.append({
                "name": name,
                "decoded": str(matched_row.get("simple_name", "")),
                "risk": risk,
                "description": str(matched_row.get("side_effects", ""))
            })

            if risk.lower() in ["Medium", "High"]:
                harmful.append(name)
        else:
            if part.lower() in seen:
                continue
            seen.add(part.lower())

            ingredients_output.append({
                "name": part.title(),
                "decoded": "Unknown",
                "risk": "Not Found",
                "description": "Ingredient not in database"
            })

    # 5. Product Suggestions (With Links)
    product_type = detect_product_type(full_text)
    product_suggestions = []

    if not products_df.empty:
        for _, p in products_df.iterrows():
            try:
                price = int(float(p.get("price", 0)))
                if not (min_budget <= price <= max_budget):
                    continue

                p_name = str(p.get("name", "")).lower()
                p_cat = str(p.get("category", "")).lower()

                # Suggest products based on the detected type (or suggest anything if type is unknown)
                if product_type == "unknown" or product_type in p_name or product_type in p_cat or ("hair" in p_cat and product_type == "shampoo"):
                    product_suggestions.append({
                        "name": str(p.get("name", "")),
                        "price": price,
                        "rating": str(p.get("rating", "N/A")),
                        "description": str(p.get("description", "")),
                        "category": str(p.get("category", "")),
                        "link": str(p.get("link", "N/A")) # Requirement 3: Includes links for purchase!
                    })
            except Exception:
                continue

    # 6. Home Remedies (Requirement 4: Exclude for eye products)
    home_remedies = []
    if not is_eye_product(full_text) and not home_remedies_df.empty:
        for _, r in home_remedies_df.iterrows():
            remedy_name = str(r.get("remedy_name", r.get("remedy_name", "Unknown")))
            home_remedies.append({
                "remedy_name": remedy_name,
                "issue": str(r.get("issue", "Unknown")),
                "description": str(r.get("description", "No description"))
            })

    return {
        "extracted_text": ingredients_text,
        "product_type_detected": product_type,
        "ingredients": ingredients_output,
        "harmful_ingredients": harmful,
        "product_suggestions": product_suggestions[:5],
        "home_remedies": home_remedies[:5] # Returns up to 5 remedies, empty if eye product
    }

# ====================== CHAT ======================
@app.post("/chat")
async def chat(request: dict):
    user_message = str(request.get("message", "")).lower()
    
    # Remove punctuation for clean matching
    clean_message = re.sub(r'[^\w\s]', '', user_message)
    
    # Filter out common stop words so words like "is", "a", "good" don't match random products
    stop_words = {"is", "a", "an", "the", "for", "my", "i", "need", "want", "any", "some", "good", "best", "what", "are", "there"}
    message_words = {w for w in clean_message.split() if w not in stop_words and len(w) > 2}

    min_budget = int(request.get("min_budget", 0))
    max_budget = int(request.get("max_budget", 999999))

    product_results = []
    food_results = []
    remedy_results = []

    # ================= FOOD DETECTION =================
    food_keywords = {"food", "eat", "drinks", "snacks", "chips", "juice", "makhana", "chana", "oats", "healthy", "diet","ice-creem","snack","beverage","biscuit","cookie","sweet","sugar","candy","chocolate"}
    is_food_query = any(word in message_words for word in food_keywords)

    # ================= SEARCH LOGIC =================
    if is_food_query and not food_df.empty:
        for _, food_item in food_df.iterrows():
            combined = (str(food_item.get("name", "")) + " " + str(food_item.get("description", ""))).lower()
            if any(word in combined for word in message_words):
                try:
                    price = int(float(food_item.get("price", 0)))
                    if min_budget <= price <= max_budget:
                        food_results.append({
                            "name": str(food_item.get("name", "")),
                            "description": str(food_item.get("description", "")),
                            "price": price
                        })
                except:
                    pass

    elif not products_df.empty:
        for _, product in products_df.iterrows():
            combined = (str(product.get("name", "")) + " " + str(product.get("category", ""))).lower()
            if any(word in combined for word in message_words):
                try:
                    price = int(float(product.get("price", 0)))
                    if min_budget <= price <= max_budget:
                        product_results.append({
                            "name": str(product.get("name", "")),
                            "price": price,
                            "rating": str(product.get("rating", "N/A")),
                            "review_snippet": str(product.get("review_snippet", "No reviews")),
                            "description": str(product.get("description", "")),
                            "category": str(product.get("category", "")),
                            "link": str(product.get("link", "N/A"))
                        })
                except:
                    pass

    # ================= REMEDY SEARCH =================
    seen = set()
    if not home_remedies_df.empty:
        for _, r in home_remedies_df.iterrows():
            combined = (str(r.get("issue", "")) + " " + str(r.get("remedy_name", "")) + " " + str(r.get("description", ""))).lower()
            if any(word in combined for word in message_words):
                key = str(r.get("remedy_name", ""))
                if key not in seen:
                    seen.add(key)
                    remedy_results.append({
                        "issue": str(r.get("issue", "")),
                        "remedy_name": key,
                        "description": str(r.get("description", ""))
                    })

    if not product_results and not food_results and not remedy_results:
        return {
            "reply": "❌ No results found. Please try different keywords.",
            "products": [],
            "food_suggestions": [],
            "home_remedies": []
        }

    return {
        "reply": "Here are your results 😊",
        "products": product_results[:5],
        "food_suggestions": food_results[:5],
        "home_remedies": remedy_results[:5]
    }
