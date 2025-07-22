# aiagent/model.py

import configparser
from openai import AzureOpenAI

# Load config
config = configparser.ConfigParser()
config.read("config/config.ini")

client = AzureOpenAI(
    api_key=config["azure_openai"]["api_key"],
    api_version=config["azure_openai"]["api_version"],
    azure_endpoint=config["azure_openai"]["endpoint"],
)

deployment_name = config["azure_openai"]["deployment_name"]

def call_agent(prompt, model_name=None):
    response = client.chat.completions.create(
        model=deployment_name,  # This is your Azure deployment name
        messages=[
            {"role": "system", "content": "You are a helpful AI assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=500
    )
    return response.choices[0].message.content.strip()
