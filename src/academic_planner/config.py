import os
from dotenv import load_dotenv
load_dotenv()
SEED = int(os.getenv("SEED", "20261022"))
DATABASE_URL = os.getenv("DATABASE_URL")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "data/generated")
