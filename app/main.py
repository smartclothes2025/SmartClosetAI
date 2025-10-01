# app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import logging, os
from app.api.v1.router import api_router

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="SmartClosetAI API")

# CORS：多加 5175 埠，或開發時全部允許 "*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        # 以下開發時可暫時開放所有 origin
        # "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"message": "智慧衣櫃後端啟動成功"}

UPLOAD_DIR = "uploaded_images"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount(f"/{UPLOAD_DIR}", StaticFiles(directory=UPLOAD_DIR), name=UPLOAD_DIR)
