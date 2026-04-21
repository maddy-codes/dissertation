from strings.paths import NL_PATH, TB_PATH, TRANS_PATH, FILE_PATH_OUT
from strings.assistant import (
    API_VERSION,
    ASSISTANT_ID,
    DEPLOYED_MODEL_NAME,
    MAX_BATCH_SIZE,
)
from helpers.data_processors import xero_info_to_message
from helpers.mappers import xero_iris_mapper
from setup.assistant_initialiser import client_initialisation, retrieve_assistant
from helpers.runners import make_thread, run_thread
from helpers.utility import save_systematic_output
from helpers.email_service import send_email
import os
import dotenv

dotenv.load_dotenv()


def run_all(
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_ENDPOINT,
    FILE_PATH_OUT,
    API_VERSION,
    ASSISTANT_ID,
    DEPLOYED_MODEL_NAME,
    MAX_BATCH_SIZE,
    messages,
    mp_df,
    client_initialisation,
    retrieve_assistant,
    make_thread,
    run_thread,
    save_systematic_output,
    emit_event=None,
):

    all_responses = []

    # initialise client
    client = client_initialisation(
        AZURE_OPENAI_API_KEY=AZURE_OPENAI_API_KEY,
        API_VERSION=API_VERSION,
        AZURE_OPENAI_ENDPOINT=AZURE_OPENAI_ENDPOINT,
    )

    for message in messages:
        if emit_event:
            emit_event("account_start", account=message["name"], message=f"Analysing {message['name']}...")
            
        # Making thread from messages
        thread = make_thread(
            client=client, message=message["message"], MAX_BATCH_SIZE=MAX_BATCH_SIZE
        )
        # running thread
        try:
            if emit_event:
                emit_event("account_progress", account=message["name"], message="Generating narrative synthesis...")
                
            response = run_thread(
                client=client, thread=thread, ASSISTANT_ID=ASSISTANT_ID
            )
            mp_df.loc[mp_df["xero_names"] == message["name"], "ai_summary"] = response

            all_responses.append(response)
            if emit_event:
                emit_event("account_complete", account=message["name"], synthesis=response)
                
        except Exception as e:
            if emit_event:
                emit_event("account_error", account=message["name"], logic=str(e))
            print("*******************", message["name"], "*******************")
            print("FAILED TO PROCESS", e)
            response = "FAILED TO PROCESS"
            all_responses.append(response)
            mp_df.loc[mp_df["xero_names"] == message["name"], "ai_summary"] = response

    mp_df.to_csv(FILE_PATH_OUT)



    # save outputs to file
    save_systematic_output(lines=all_responses, name=FILE_PATH_OUT)


if __name__ == "__main__":
    pass
