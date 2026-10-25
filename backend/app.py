from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

from outlook.router import router as outlook_router

load_dotenv()

app = FastAPI(
    title="Matrix Bridge API",
    description="Bidirectional context sync between Claude and ChatGPT",
    version="0.1.0"
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Integration points
app.include_router(outlook_router)

# Routes (to be implemented)
@app.get("/")
def read_root():
    return {
        "message": "Matrix Bridge API",
        "status": "online",
        "version": "0.1.0",
        "integrations": ["outlook"]
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
