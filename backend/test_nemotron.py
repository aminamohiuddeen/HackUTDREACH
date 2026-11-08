from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.getenv("NVIDIA_API_KEY"),
)

r = client.chat.completions.create(
    model="nvidia/nemotron-3.5-super-vl-120b-a12b",
    messages=[{"role": "user", "content": "Say hello in one word."}],
    max_tokens=50,
)

msg = r.choices[0].message
print("content:", repr(msg.content))
print("reasoning:", repr(getattr(msg, "reasoning_content", None)))
print("tool_calls:", getattr(msg, "tool_calls", None))
print("finish_reason:", r.choices[0].finish_reason)