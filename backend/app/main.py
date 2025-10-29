from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import Base, engine
from .routers.api import router

app = FastAPI(
    title="Taipei Hackathon Microservice",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/docs/openapi.json",
)

origins = [
    "http://localhost:5173",
    "http://localhost:4173",
    "http://localhost:3000",
    "http://localhost:8080",
    "https://townpass-microservice.web.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api", tags=["API"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the Taipei Hackathon Microservice!"}

Base.metadata.create_all(bind=engine)