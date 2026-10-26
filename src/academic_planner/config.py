import os
from dotenv import load_dotenv
load_dotenv()
SEED = int(os.getenv("SEED", "20261022"))
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://planner:planner@localhost:5432/academic_planner")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "data/generated")
