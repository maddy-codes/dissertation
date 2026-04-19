import time


def make_thread(client, message, MAX_BATCH_SIZE):
    # Create a thread
    thread = client.beta.threads.create()

    # Add a user question to the thread
    batch_size = MAX_BATCH_SIZE
    batches = [message[i : i + batch_size] for i in range(0, len(message), batch_size)]
    print("number of batches:", len(batches))
    for batch in batches:
        message = client.beta.threads.messages.create(
            thread_id=thread.id, role="user", content=batch
        )
    return thread


def run_thread(client, thread, ASSISTANT_ID):
    # Run the thread
    run = client.beta.threads.runs.create(
        thread_id=thread.id, assistant_id=ASSISTANT_ID
    )

    # Looping until the run completes or fails
    while run.status in ["queued", "in_progress", "cancelling"]:
        time.sleep(1)
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

    if run.status == "completed":
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        print(messages.data[0].content[0].text.value)
        return messages.data[0].content[0].text.value

    elif run.status == "requires_action":
        # the assistant requires calling some functions
        # and submit the tool outputs back to the run
        return "require_action"

    else:
        print(run.status)
        return run.status
