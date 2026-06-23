from langchain_openai import ChatOpenAI
from env_utils import *

llm = ChatOpenAI(
    model='deepseek-v4-flash',
    temperature=0.5,
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_API_URL
)
