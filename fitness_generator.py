import json
import os
import re
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, List

# Load environment variables from .env.local or .env
from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph


# -------- Helper: Clean LLM JSON output --------
def clean_json_str(s: str) -> str:
    """
    Remove markdown code fences (``````), optional 'json' language hint,
    then strip whitespace, so json.loads() can parse it cleanly.
    """
    if not isinstance(s, str):
        return ""
    s = s.strip()
    # Remove opening ```
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    # Remove closing ```
    s = re.sub(r"\s*```$", "", s)
    return s.strip()


# --------- USER PROFILE MODEL ----------
@dataclass
class UserProfile:
    user_id: str
    age: int
    height: str
    weight: str
    injuries: str
    workout_days: List[str]
    fitness_goal: str
    fitness_level: str
    dietary_restrictions: str


# --------- WORKFLOW STATE ----------
class FitnessState(dict):
    user_profile: UserProfile
    workout_plan: Dict[str, Any]
    diet_plan: Dict[str, Any]
    validated_workout: Dict[str, Any]
    validated_diet: Dict[str, Any]
    final_plan: Dict[str, Any]
    errors: List[str]


# --------- MAIN GENERATOR ----------
class FitnessPlanGenerator:
    def __init__(self):
        groq_key = os.getenv("GROQ_API_KEY")
        print(
            "[DEBUG] GROQ_API_KEY loaded:", groq_key[:6] + "..." if groq_key else None
        )
        self.llm = ChatGroq(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            groq_api_key=groq_key,
        )
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(FitnessState)
        workflow.add_node("generate_workout", self.generate_workout_plan)
        workflow.add_node("generate_diet", self.generate_diet_plan)
        workflow.add_node("validate_workout", self.validate_workout_plan)
        workflow.add_node("validate_diet", self.validate_diet_plan)
        workflow.add_node("finalize_plan", self.finalize_plan)

        workflow.set_entry_point("generate_workout")
        workflow.add_edge("generate_workout", "generate_diet")
        workflow.add_edge("generate_diet", "validate_workout")
        workflow.add_edge("validate_workout", "validate_diet")
        workflow.add_edge("validate_diet", "finalize_plan")
        workflow.add_edge("finalize_plan", END)
        return workflow.compile()

    # -------- FINALIZE ----------
    def finalize_plan(self, state: FitnessState) -> FitnessState:
        state["final_plan"] = {
            "success": len(state.get("errors", [])) == 0,
            "workout_plan": state.get("validated_workout", {}),
            "diet_plan": state.get("validated_diet", {}),
            "errors": state.get("errors", []),
        }
        return state

    # -------- WORKOUT GENERATION ----------
    def generate_workout_plan(self, state: FitnessState) -> FitnessState:
        user = state["user_profile"]
        workout_prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content="""
You are an experienced fitness coach creating personalized workout plans.
CRITICAL SCHEMA INSTRUCTIONS:
- Your output MUST contain ONLY the fields specified below, NO ADDITIONAL FIELDS
- "sets" and "reps" MUST ALWAYS be NUMBERS, never strings
- Return ONLY a valid JSON object with this EXACT structure:
{
  "schedule": ["Monday", "Wednesday", "Friday"],
  "exercises": [
    {
      "day": "Monday",
      "routines": [
        {
          "name": "Exercise Name",
          "sets": 3,
          "reps": 10
        }
      ]
    }
  ]
}
"""
                ),
                HumanMessage(
                    content=f"""
Create a personalized workout plan based on:
Age: {user.age}
Height: {user.height}
Weight: {user.weight}
Injuries or limitations: {user.injuries}
Available days for workout: {', '.join(user.workout_days)}
Fitness goal: {user.fitness_goal}
Fitness level: {user.fitness_level}
"""
                ),
            ]
        )
        try:
            response = self.llm.invoke(workout_prompt.format_messages())
            print("[DEBUG] LLM workout raw response:", repr(response.content))
            cleaned = clean_json_str(response.content)
            state["workout_plan"] = json.loads(cleaned)
        except Exception as e:
            print("[ERROR] LLM workout exception:", e)
            state["errors"] = state.get("errors", []) + [
                f"Workout generation error: {str(e)}"
            ]
            schedule = (
                user.workout_days
                if isinstance(user.workout_days, list)
                else [str(user.workout_days)]
            )
            state["workout_plan"] = {
                "schedule": schedule,
                "exercises": [
                    {
                        "day": day,
                        "routines": [
                            {"name": "Push-ups", "sets": 3, "reps": 10},
                            {"name": "Squats", "sets": 3, "reps": 15},
                            {"name": "Plank", "sets": 3, "reps": 30},
                        ],
                    }
                    for day in schedule
                ],
            }
        return state

    # --------- DIET GENERATION ----------
    def generate_diet_plan(self, state: FitnessState) -> FitnessState:
        user = state["user_profile"]
        diet_prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content="""
You are an experienced nutrition coach creating personalized diet plans.
CRITICAL SCHEMA INSTRUCTIONS:
- Your output MUST contain ONLY the fields specified below, NO ADDITIONAL FIELDS
- "dailyCalories" MUST be a NUMBER, not a string
- Return ONLY a valid JSON object with this EXACT structure:
{
  "dailyCalories": 2000,
  "meals": [
    {
      "name": "Breakfast",
      "foods": ["Oatmeal with berries", "Greek yogurt", "Black coffee"]
    },
    {
      "name": "Lunch",
      "foods": ["Grilled chicken salad", "Whole grain bread", "Water"]
    }
  ]
}
"""
                ),
                HumanMessage(
                    content=f"""
Create a personalized diet plan based on:
Age: {user.age}
Height: {user.height}
Weight: {user.weight}
Fitness goal: {user.fitness_goal}
Dietary restrictions: {user.dietary_restrictions}
"""
                ),
            ]
        )
        try:
            response = self.llm.invoke(diet_prompt.format_messages())
            print("[DEBUG] LLM diet raw response:", repr(response.content))
            cleaned = clean_json_str(response.content)
            state["diet_plan"] = json.loads(cleaned)
        except Exception as e:
            print("[ERROR] LLM diet exception:", e)
            state["errors"] = state.get("errors", []) + [
                f"Diet generation error: {str(e)}"
            ]
            state["diet_plan"] = {
                "dailyCalories": 2000,
                "meals": [
                    {
                        "name": "Breakfast",
                        "foods": ["Oatmeal with berries", "Greek yogurt", "Coffee"],
                    },
                    {
                        "name": "Lunch",
                        "foods": ["Grilled chicken salad", "Brown rice", "Water"],
                    },
                    {
                        "name": "Dinner",
                        "foods": ["Salmon", "Vegetables", "Sweet potato"],
                    },
                ],
            }
        return state

    # -------- WORKOUT VALIDATION ----------
    def validate_workout_plan(self, state: FitnessState) -> FitnessState:
        try:
            plan = state["workout_plan"]
            validated_plan = {"schedule": plan.get("schedule", []), "exercises": []}
            for ex in plan.get("exercises", []):
                routines = []
                for r in ex.get("routines", []):
                    sets = int(r.get("sets", 1))
                    reps = int(r.get("reps", 10))
                    routines.append(
                        {"name": r.get("name", "Exercise"), "sets": sets, "reps": reps}
                    )
                validated_plan["exercises"].append(
                    {"day": ex.get("day", ""), "routines": routines}
                )
            state["validated_workout"] = validated_plan
        except Exception as e:
            state["errors"] = state.get("errors", []) + [
                f"Workout validation error: {str(e)}"
            ]
        return state

    # -------- DIET VALIDATION ----------
    def validate_diet_plan(self, state: FitnessState) -> FitnessState:
        try:
            plan = state.get("diet_plan", {})
            meals = plan.get("meals", [])
            if not isinstance(meals, list):
                meals = []
            validated_meals = []
            for meal in meals:
                name = meal.get("name", "Meal")
                foods = meal.get("foods", [])
                if not isinstance(foods, list):
                    foods = []
                validated_meals.append({"name": name, "foods": foods})
            state["validated_diet"] = {
                "dailyCalories": int(plan.get("dailyCalories", 2000)),
                "meals": validated_meals,
            }
        except Exception as e:
            state["errors"] = state.get("errors", []) + [
                f"Diet validation error: {str(e)}"
            ]
        return state

    # -------- MAIN ENTRY ----------
    def generate_fitness_plan(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            user_profile = UserProfile(
                user_id=user_data["user_id"],
                age=int(user_data["age"]),
                height=user_data["height"],
                weight=user_data["weight"],
                injuries=user_data.get("injuries", "None"),
                workout_days=user_data["workout_days"],
                fitness_goal=user_data["fitness_goal"],
                fitness_level=user_data["fitness_level"],
                dietary_restrictions=user_data.get("dietary_restrictions", "None"),
            )
            state = {
                "user_profile": user_profile,
                "workout_plan": {},
                "diet_plan": {},
                "validated_workout": {},
                "validated_diet": {},
                "final_plan": {},
                "errors": [],
            }
            result = self.graph.invoke(state)
            final = result["final_plan"]
            return {
                "success": final.get("success", False),
                "workout_plan": final.get("workout_plan", {}),
                "diet_plan": final.get("diet_plan", {}),
                "errors": final.get("errors", []),
            }
        except Exception as e:
            return {"success": False, "error": f"LangGraph execution error: {str(e)}"}


# --------- GLOBAL INSTANCE ----------
generator = FitnessPlanGenerator()


# --------- OPTIONAL HTTP HANDLER ----------
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(length)
            request_data = json.loads(data.decode("utf-8"))
            result = generator.generate_fitness_plan(request_data)
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(
                json.dumps({"success": False, "error": str(e)}).encode("utf-8")
            )

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(
            json.dumps(
                {
                    "status": "healthy",
                    "message": "Fitness Generator API with Groq/LangGraph",
                }
            ).encode("utf-8")
        )
