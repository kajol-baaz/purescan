from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import easyocr
import numpy as np
import cv2
import pandas as pd
import re
from difflib import get_close_matches

app = FastAPI()

# ================== STATIC ==================
app.mount("/static", StaticFiles(directory="../../frontend", html=True), name="frontend")

# ================== CORS ==================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================== LOAD ==================
reader = easyocr.Reader(['en'], gpu=False)

ingredients_df = pd.read_csv("data/ingredients.csv")
products_df = pd.read_csv("data/products.csv")
home_remedies_df = pd.read_csv("data/home_remedies.csv")
food_df = pd.read_csv("data/food.csv")

ingredients_df['name'] = ingredients_df['name'].str.lower()

# ================== SMART PRODUCT MAP ==================
PRODUCT_MAP = {
    "mascara": ["mascara", "lash", "eye", "eyelash"],
    "shampoo": ["shampoo", "hair"],
    "facewash": ["face", "cleanser", "wash", "soap"],
    "beverage": ["drink", "soda", "cola", "juice", "beverage", "soft drink"],
    "oil": ["oil", "hair oil"]
}

def detect_product_type(text):
    text = text.lower()
    for key, keywords in PRODUCT_MAP.items():
        if any(k in text for k in keywords):
            return key
    return None

NO_REMEDY_PRODUCTS = ["mascara", "eyeliner", "eye liner", "kajal"]

def is_eye_product(text):
    text = text.lower()
    return any(x in text for x in NO_REMEDY_PRODUCTS)

# ====================== SCAN ======================
@app.post("/purescan")
async def scan(file: UploadFile = File(...), min_budget: int = Form(100), max_budget: int = Form(2000)):

    contents = await file.read()
    image = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(image, cv2.IMREAD_COLOR)

    if image is None:
        return {"error": "Invalid image"}

    result = reader.readtext(image)
    full_text = " ".join([r[1] for r in result]).lower()

    # ===== EXTRACT =====
    match = re.search(
        r'ingredient[s]?\s*[:\-]?\s*(.*?)(usage|direction|how to use|warning|apply|$)',
        full_text,
        re.IGNORECASE | re.DOTALL
    )

    ingredients_text = match.group(1) if match else full_text

    ingredients_text = re.sub(r'[^a-zA-Z0-9\s,.-]', ' ', ingredients_text)
    ingredients_text = re.sub(r'\s+', ' ', ingredients_text).strip()

    parts = [p.strip() for p in ingredients_text.split(",") if p.strip()]

    ingredients_output = []
    harmful = []

    for part in parts:
        part_lower = part.lower()
        found = False

        for _, row in ingredients_df.iterrows():
            ing = row['name']

            if ing in part_lower:
                risk = str(row.get("risk_level", "Unknown"))

                ingredients_output.append({
                    "name": ing.title(),
                    "decoded": row.get("simple_name"),
                    "risk": risk,
                    "description": row.get("side_effects")
                })

                if risk.lower() in ["medium", "high"]:
                    harmful.append(ing)

                found = True
                break

        if not found:
            ingredients_output.append({
                "name": part,
                "decoded": "Unknown",
                "risk": "Unknown",
                "description": "Not in database"
            })

    # ===== REMOVE DUPLICATES =====
    seen = set()
    ingredients_output = [i for i in ingredients_output if not (i["name"] in seen or seen.add(i["name"]))]

    # ===== SMART PRODUCT TYPE DETECTION =====
    product_type = detect_product_type(full_text)

    # ================== PRODUCTS ==================
    product_suggestions = []

    for _, p in products_df.iterrows():
        try:
            price = int(p.get("price", 0))

            if not (min_budget <= price <= max_budget):
                continue

            category = str(p.get("category", "")).lower()
            name = str(p.get("name", "")).lower()

            # 🎯 STRICT MATCH (IMPORTANT FIX)
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
                    "category": p.get("category")
                })

        except:
            continue

    # ================== REMEDIES ==================
    home_remedies = []

    # ❌ BLOCK for mascara/eyeliner
    if not is_eye_product(full_text):
        for _, r in home_remedies_df.iterrows():
            home_remedies.append({
                "remedy": r["remedy"],
                "issue": r["issue"],
                "description": r["description"]
            })


    return {
        "extracted_text": ingredients_text,
        "ingredients": ingredients_output,
        "product_suggestions": product_suggestions[:5],
        "home_remedies": home_remedies[:5],
        "food_alternatives": []
    }


# ========= ============================== CHAT ======================
@app.post("/chat")
async def chat(request: dict):

    user_message = (request.get("message") or "").lower()
    min_budget = int(request.get("min_budget", 0))
    max_budget = int(request.get("max_budget", 999999))

    message_words = set(user_message.split())

    product_results = []
    food_results = []
    remedy_results = []

    # ================= DETECT FOOD =================
    food_keywords = {
        "food", "eat", "drink", "snack", "chips", "coconut",
        "juice", "makhana", "chana", "oats", "diet", "healthy"
    }

    is_food_query = any(word in user_message for word in food_keywords)

    # ================= FOOD SEARCH =================
    if is_food_query:

        for _, food_item in food_df.iterrows():

            food_name = str(food_item.get("name", "")).lower()
            food_desc = str(food_item.get("description", "")).lower()
            food_alt = str(food_item.get("healthy_alternative", "")).lower()

            combined_text = food_name + " " + food_desc + " " + food_alt

            if any(word in combined_text for word in message_words):

                try:
                    price = int(food_item.get("price", 0))
                except:
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

            if any(word in combined_text for word in message_words):

                try:
                    price = int(product.get("price", 0))
                except:
                    price = 0

                if min_budget <= price <= max_budget:

                    product_results.append({
                        "name": product.get("name", "N/A"),
                        "price": price,
                        "description": product.get("description", "N/A"),
                        "category": product.get("category", "N/A")
                    })

    # ================= HOME REMEDIES (FIXED PROPERLY) =================
    seen_remedies = set()

    for _, remedy in home_remedies_df.iterrows():

        issue = str(remedy.get("issue", "")).lower()
        remedy_name = str(remedy.get("remedy_name", "")).lower()  # FIXED COLUMN
        description = str(remedy.get("description", "")).lower()

        combined_text = issue + " " + remedy_name + " " + description

        if any(word in combined_text for word in message_words):

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
            "reply": "❌ No results found. Try keywords like shampoo, face wash, coconut water, chips, etc.",
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