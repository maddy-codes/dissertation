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
    NL_PATH,
    TB_PATH,
    TRANS_PATH,
    FILE_PATH_OUT,
    API_VERSION,
    ASSISTANT_ID,
    DEPLOYED_MODEL_NAME,
    MAX_BATCH_SIZE,
    xero_info_to_message,
    xero_iris_mapper,
    client_initialisation,
    retrieve_assistant,
    make_thread,
    run_thread,
    save_systematic_output,
    recipient_email,
):

    all_responses = []

    # initialise client
    client = client_initialisation(
        AZURE_OPENAI_API_KEY=AZURE_OPENAI_API_KEY,
        API_VERSION=API_VERSION,
        AZURE_OPENAI_ENDPOINT=AZURE_OPENAI_ENDPOINT,
    )

    # retrieve assistant
    # assistant = retrieve_assistant(client=client,ASSISTANT_ID=ASSISTANT_ID,DEPLOYED_MODEL_NAME=DEPLOYED_MODEL_NAME)

    # making message
    # variance_analysis_threshold=VARIANCE_ANALYSIS_VALUE,
    messages = xero_info_to_message(tb_path=TB_PATH, transactions_path=TRANS_PATH)
    m2, mp_df = xero_iris_mapper(
        NL_PATH=NL_PATH, TB_PATH=TB_PATH, TRANS_PATH=TRANS_PATH
    )

    for message in messages:
        # Making thread from messages
        thread = make_thread(
            client=client, message=message["message"], MAX_BATCH_SIZE=MAX_BATCH_SIZE
        )
        # running thread
        try:
            print("*******************", message["name"], "*******************")
            response = run_thread(
                client=client, thread=thread, ASSISTANT_ID=ASSISTANT_ID
            )
            mp_df.loc[mp_df["xero_names"] == message["name"], "ai_summary"] = response

            all_responses.append(response)
        except Exception as e:
            print("*******************", message["name"], "*******************")
            print("FAILED TO PROCESS", e)
            response = "FAILED TO PROCESS"
            all_responses.append(response)
            mp_df.loc[mp_df["xero_names"] == message["name"], "ai_summary"] = response

    mp_df.to_csv(FILE_PATH_OUT)

    # email meta data
    subject = "Report for the Generated Reviews | PHM Accountants"
    file_path = FILE_PATH_OUT
    body = f"""Hello,
    
Please find the attached report for the generated reviews. 

The report contains the generated reviews for the accounts in the trial balance, based on the transactions in the account transactions file and the nominal ledger file. 

The link to the generated reviews is as follows: https://ai.phm-accountants.co.uk/result/

Regards,
Technical Team,
PHM Accountants
    
    """
    recipient_list = [
        {"address": f"{recipient_email}", "displayName": "PHM Accountant"},
        # {"address": "jatinarora2689@gmail.com", "displayName": "Mr. Jatin Arora"}
    ]
    sender_address = "donotreply@e444ea86-37e7-4a7d-857b-261cf490d7ce.azurecomm.net"

    # send email
    send_email(subject, file_path, body, recipient_list, sender_address)

    # save outputs to file
    save_systematic_output(lines=all_responses, name=FILE_PATH_OUT)
    # with open("mapped.json", "w") as f:
    #     f.write(json.dumps(m2))


if __name__ == "__main__":

    run_all(
        os.environ.get("AZURE_OPENAI_API_KEY"),
        os.environ.get("AZURE_OPENAI_ENDPOINT"),
        NL_PATH,
        TB_PATH,
        TRANS_PATH,
        FILE_PATH_OUT,
        API_VERSION,
        ASSISTANT_ID,
        DEPLOYED_MODEL_NAME,
        MAX_BATCH_SIZE,
        xero_info_to_message,
        xero_iris_mapper,
        client_initialisation,
        retrieve_assistant,
        make_thread,
        run_thread,
        save_systematic_output,
        "s.khan@phm-accountants.co.uk",
    )
