# -*- coding: utf-8 -*-
"""
VOD Player Backend - FastAPI Application

Provides REST API for browsing recordings and generating presigned playback URLs.
"""
import os
import sys

# Add project root to Python path for importing src modules (vod-player/backend/app/main.py -> 4 levels up)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers.api import router as api_router

settings = get_settings()

app = FastAPI(
    title="VOD Player API",
    description="API for browsing and playing recorded live streams",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "vod_enabled": settings.vod_enabled}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.server_port,
        reload=True
    )
