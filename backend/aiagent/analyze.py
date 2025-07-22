import openai
import configparser
import os
import sys

# Load Azure OpenAI config from config.ini
config = configparser.ConfigParser()
config.read(os.path.join(os.path.dirname(__file__), '../config/config.ini'))

azure_conf = config['azure_openai']
openai.api_type = "azure"
openai.api_base = azure_conf['endpoint']
openai.api_version = azure_conf['api_version']
openai.api_key = azure_conf['api_key']
DEPLOYMENT_NAME = azure_conf['deployment_name']

def analyze(logs: str) -> str:
    messages = [
        {"role": "system", "content": "You are a debugging expert."},
        {"role": "user", "content": f"Analyze the following logs and explain the issue:\n\n{logs}"}
    ]
    response = openai.ChatCompletion.create(
        engine=DEPLOYMENT_NAME,
        messages=messages,
        temperature=0.2
    )
    return response['choices'][0]['message']['content']

if __name__ == "__main__":
    logs = sys.stdin.read()
    print(analyze(logs))
