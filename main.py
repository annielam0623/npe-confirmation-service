from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"status": "NPE confirmation service running"}

@app.get("/confirm")
def confirm(token: str):
    return {"confirmed": True, "token": token}