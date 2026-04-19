###Basic Imports###
import tiktoken
from openai import OpenAI, AzureOpenAI
from strings.assistant import (
    API_VERSION,
    ASSISTANT_ID,
    INSTRUCTION,
    MODEL,
    NAME,
    TEMPRATURE,
    TOP_P,
    DEPLOYED_MODEL_NAME,
)

# from creds.creds import OPENAI_KEY, AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT


###Client Initialiser###
def client_initialisation(AZURE_OPENAI_API_KEY, API_VERSION, AZURE_OPENAI_ENDPOINT):
    client = AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        api_version=API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
    )
    return client


###Assistant Maker###
def make_assistant(client, INSTRUCTION):
    assistant = client.beta.assistants.create(
        instructions=INSTRUCTION,
        model=DEPLOYED_MODEL_NAME,  # replace with model deployment name.
        tools=[{"type": "code_interpreter"}],
    )
    return assistant


###Update Assitant###
def update_assistant(client, ASSISTANT_ID, INSTRUCTION, TEMPRATURE, NAME, TOP_P):
    try:
        client.beta.assistants.update(
            assistant_id=ASSISTANT_ID,
            instructions=INSTRUCTION,
            temperature=TEMPRATURE,
            name=NAME,
            top_p=TOP_P,
        )
        return "DONE"
    except Exception as e:
        print(e)
        return "FAILED"


###Assistant Retriver###
def retrieve_assistant(client, ASSISTANT_ID, DEPLOYED_MODEL_NAME):
    assistant = client.beta.assistants.retrieve(assistant_id=ASSISTANT_ID)
    return assistant


###Empty assistabt run functions###
def run_assistant():
    pass
