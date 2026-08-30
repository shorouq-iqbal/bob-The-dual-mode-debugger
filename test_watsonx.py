import os
from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference

# Read credentials from environment variables
api_key = os.getenv("WATSONX_API_KEY", "")
project_id = os.getenv("WATSONX_PROJECT_ID", "")
url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")

print(f"Testing Connection:")
print(f"- URL: {url}")
print(f"- Project ID: {project_id}")
print(f"- API Key: {'*' * (len(api_key) - 4) + api_key[-4:] if len(api_key) >= 4 else 'NOT SET'}\n")

if not api_key or not project_id:
    print("❌ Error: WATSONX_API_KEY or WATSONX_PROJECT_ID environment variables are missing.")
    exit(1)

try:
    model = ModelInference(
        model_id = "ibm/granite-4-h-small",
        credentials=Credentials(api_key=api_key, url=url),
        project_id=project_id,
    )
    
    response = model.chat(messages=[{"role": "user", "content": "Respond with 'Watsonx is connected successfully!'" }])
    print("✅ SUCCESS! Granite responded:")
    print(response["choices"][0]["message"]["content"])

except Exception as e:
    print("❌ Connection Failed:")
    print(e)

