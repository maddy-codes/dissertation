import json
import pandas as pd


def make_stable(path: str) -> pd.DataFrame:
    """This remoes the unnecessary part from the Xero Trial balance and account transactions to make it a perfect format for processing to be done.

    Keyword arguments:
    path : Path to the excel File
    Return: DataFrame of document ready to be processed furthur.
    """

    base_data = pd.read_excel(path)
    df = base_data.iloc[4:]
    df.columns = list(base_data.iloc[3])
    df.index = list(range(len(df)))
    return df.fillna(value="")


def change_trial_balance(trial_balance: pd.DataFrame) -> pd.DataFrame:
    """This Functions processes the trial balance and returs a DataFrame with Calculated Variance.

    Keyword arguments:
    trial_balance -- DataFrame of TrialBalance ready to be Processed.
    Return: Returns a processed dataframe with variance calculated.
    """

    date_col = " ".join(
        [
            str(trial_balance.columns[-1].split()[0]),
            str(trial_balance.columns[-1].split()[1]),
            str(int(trial_balance.columns[-1].split()[2]) + 1),
        ]
    )
    for i, j, k in zip(
        trial_balance[trial_balance.columns[3]],
        trial_balance[trial_balance.columns[4]],
        trial_balance[trial_balance.columns[0]],
    ):
        if i != "":
            trial_balance.loc[
                trial_balance[trial_balance[trial_balance.columns[0]] == k].index,
                date_col,
            ] = i
        else:
            trial_balance.loc[
                trial_balance[trial_balance[trial_balance.columns[0]] == k].index,
                date_col,
            ] = -j

    trial_balance["varience"] = abs(trial_balance[trial_balance.columns[-1]]) - abs(
        trial_balance[trial_balance.columns[-2]]
    )
    var_percent = []
    for i, j in zip(
        list(trial_balance[trial_balance.columns[-2]]),
        list(trial_balance[trial_balance.columns[-3]]),
    ):
        var_percent.append(calculate_variance_percentage(i, j))
    trial_balance["var_percent"] = var_percent
    new_tb = pd.DataFrame(
        {
            trial_balance.columns[0]: trial_balance[trial_balance.columns[0]],
            trial_balance.columns[1]: trial_balance[trial_balance.columns[1]],
            trial_balance.columns[2]: trial_balance[trial_balance.columns[2]],
            trial_balance.columns[6]: trial_balance[trial_balance.columns[6]],
            trial_balance.columns[5]: trial_balance[trial_balance.columns[5]],
            trial_balance.columns[7]: trial_balance[trial_balance.columns[7]],
            trial_balance.columns[8]: trial_balance[trial_balance.columns[8]],
        }
    )
    return new_tb[:-1]


def process_trial_balance(path: str) -> pd.DataFrame:
    """End to End processing function of trial balance (Combination of make_stable and process_trial_balance functions).

    Keyword arguments:
    path -- path to trial balance excel.
    Return: processed dataframe of trialbalance with variance calculated.
    """

    base_tb = make_stable(path)
    processed_tb = change_trial_balance(base_tb)
    return processed_tb


def xero_info_to_message(tb_path: str, transactions_path: str) -> list:
    """Combines the Xero Trial Balance Nominals and Transactions together in a message format for LLM to process.

    Keyword arguments:
    tb_path -- path to trial balance excel.
    transactions_path -- path to the account transactions excel
    Return: returns the list of messages to be fed to trial balance.
    """

    messages = []

    mapping = make_xero_mapping(
        transactions_path=transactions_path, trial_balance_path=tb_path
    )
    # la = json.dumps(mapping)
    # with open('la.json','w') as f:
    #     f.write(la)

    trial_balance = process_trial_balance(tb_path)

    for i in trial_balance["Account"]:
        messages.append(
            {
                "name": i,
                "message": "Please process these account codes and transactions"
                + str(mapping[i]),
            }
        )

    return messages


def iris_xero_messages(NL_PATH, TB_PATH, TRANS_PATH):
    messages = []
    mapping_dict = xero_iris_mapper(
        NL_PATH=NL_PATH, TB_PATH=TB_PATH, TRANS_PATH=TRANS_PATH
    )
    for i in mapping_dict["iris_nominals"]:
        messages.append(str(i))
    return messages


from helpers.utility import calculate_variance_percentage
from helpers.mappers import make_xero_mapping, xero_iris_mapper
