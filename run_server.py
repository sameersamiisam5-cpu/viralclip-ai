import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("⚡ [J.A.R.V.I.S.] Starting AI Clipping Tool Web Dashboard")
    print("🌐 Dashboard URL: http://localhost:8000")
    print("=" * 60)
    uvicorn.run("web_app:app", host="0.0.0.0", port=8000, reload=True)
