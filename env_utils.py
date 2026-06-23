import os

from dotenv import load_dotenv

load_dotenv(override=True)

DEEPSEEK_API_KEY=os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL=os.getenv("DEEPSEEK_API_URL")

AMAP_API_KEY=os.getenv("AMAP_API_KEY")
