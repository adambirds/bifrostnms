from fastapi import FastAPI

app = FastAPI(title="BifrostNMS", version="0.0.0")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
