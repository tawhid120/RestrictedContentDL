# app.py
from fastapi import FastAPI
from fastapi.responses import Response
import os

app = FastAPI(title="RestrictedContentDL Bot Status")

@app.get("/", include_in_schema=False)
async def root_get():
    """Render health check endpoint for GET"""
    return {"status": "bot_worker_is_running_separately"}

@app.head("/", include_in_schema=False)
async def root_head():
    """Render health check endpoint for HEAD"""
    return Response(status_code=200)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
