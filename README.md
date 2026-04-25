# PureScan AI 🌿

PureScan is an AI-powered product scanner and recommendation web application. Its primary goal is to help users scan product labels (like cosmetics, skincare, and food) to analyze ingredients for risks, while also suggesting safer alternatives and home remedies that fit within a user's specific budget.

## 🚀 Features

- **Image OCR Scanning (`/purescan`)**
  Upload an image of a product label from your gallery or camera. The backend uses **EasyOCR** to extract text and smartly identifies the ingredient list. It highlights harmful ingredients based on risk levels.

- **Smart Product Suggestions & Budgeting**
  Users set a minimum and maximum budget. The app detects the product category from the scanned text and suggests alternative products that are safe and fall within the budget.

- **Food and Remedy Alternatives (`/chat`)**
  A chat-like interface where users can type queries. If the user asks about food (e.g., "chips", "coconut water"), the system fetches healthy alternatives. The app also provides natural home remedies.

- **Accessibility**
  Includes a Text-to-Speech (Read Aloud) feature on the frontend using `window.speechSynthesis`.

## 🛠️ Tech Stack

- **Backend:** Python, FastAPI, Pandas, EasyOCR, Uvicorn, OpenCV
- **Frontend:** HTML, CSS, JavaScript (jQuery)
- **Data Management:** CSV databases for ingredients, products, food, and home remedies.

## 📂 Project Structure

```
purescan/
├── FastAPI/
│   ├── app/
│   │   ├── data/          # CSV databases
│   │   └── app.py         # Main FastAPI backend
│   ├── pyproject.toml
│   └── uv.lock
└── frontend/
    ├── purescan.html      # Main Web UI
    ├── purescan.js        # Frontend Logic
    └── ...                # CSS & other UI assets
```

## 💻 How to Run Locally

### 1. Backend Setup
1. Navigate to the `FastAPI` directory.
2. Ensure you have Python 3.11+ installed.
3. Install dependencies using `uv` (or pip):
   ```bash
   uv sync
   ```
   Or manually:
   ```bash
   pip install fastapi uvicorn pandas easyocr python-multipart opencv-python-headless
   ```
4. Start the FastAPI server:
   ```bash
   uvicorn app.app:app --reload
   ```

### 2. Frontend Setup
The frontend is statically served by the backend! Just open your browser and navigate to:
```
http://127.0.0.1:8000/static/purescan.html
```

## 🐛 Recent Fixes
- Enhanced the chat search logic to filter stop words and do exact word-boundary matching.
- Prevented a `KeyError` by accurately mapping the `remedy_name` column in the database.
- Smart-filtered the home remedies output to match the detected product category.
