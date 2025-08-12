from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ✅ Import the global generator instance from fitness_generator.py
from fitness_generator import generator
from pydantic import BaseModel

app = FastAPI()
# CORS middleware (fully open)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request schema
class FitnessRequest(BaseModel):
    age: str
    weight: str
    height: str
    injuries: str
    fitness_goal: str
    workout_days: List[str]  # Accepts a list of strings
    fitness_level: str
    dietary_restrictions: str
    user_id: str


@app.post("/api/fitness_generator")
async def generate_plan(payload: FitnessRequest):
    try:
        # Convert to dict for the generator
        payload_dict = payload.dict()

        # Pass to generator and return result
        result = generator.generate_fitness_plan(payload_dict)
        return {"success": True, "data": result}

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/")
def root():
    return {"message": "Fitness API is running."}
    return {"message": "Fitness API is running."}
    return {"message": "Fitness API is running."}
    return {"message": "Fitness API is running."}
