def make_xero_mapping(transactions_path, trial_balance_path):
    # initialising the dictionary for storing the account nominal and related transactions.
    tb_transactions_dict = {}
    # loading the Trial balance and processing it using premade fuctions
    trial_balance = process_trial_balance(trial_balance_path)
    # loading the transactions database
    transactions = make_stable(transactions_path)

    # making datetime columnns as str for  transactions
    for col in transactions.columns:
        transactions[col] = transactions[col].astype(str)

    for i in trial_balance["Account"]:
        index_start = transactions[transactions[transactions.columns[0]] == i].index
        index_end = transactions[
            transactions[transactions.columns[0]] == f"Total {i.strip()}"
        ].index
        # print(i,list(index_start), list(index_end), list(transactions.loc[index_start,transactions.columns[0]]),list(transactions.loc[index_end,transactions.columns[0]]))
        if len(list(index_start)) == 0:
            tb_transactions_dict[i] = {
                "related_tb": str(trial_balance[trial_balance["Account"] == i]),
                "related_transactions": "NO RELATED TRANSACTIONS FOUND",
            }
        else:
            related_transactions = transactions.iloc[index_start[0] : index_end[0]]
            # print(related_transactions.to_dict(orient='records'))
            tb_transactions_dict[i] = {
                "related_tb": str(trial_balance[trial_balance["Account"] == i]),
                "related_transactions": json.dumps(
                    related_transactions.to_dict(orient="records")
                ),
            }
    return tb_transactions_dict


def make_iris_dict(NL_PATH, TB_PATH):

    # Mapping Dataframe
    iris_codes = []
    iris_names = []
    xero_names = []
    xero_codes = []

    # TODO: The NL file should be CSV but it is an excel file. CSV gives error atm
    df = pd.read_excel(NL_PATH)
    tb = make_stable(TB_PATH)
    iris = []
    for i, j in zip(tb[tb.columns[0]], tb[tb.columns[1]]):
        iris.append(str(i) + str(j))
    tb["iris"] = iris
    main_indexes = []
    for i in df[df[df.columns[1]] == "Narrative"].index:
        la = df.iloc[i - 2][df.columns[0]]
        main_indexes.append(i - 2)
    searching_dict = {"iris_nominals": []}
    end_point = len(main_indexes) - 1
    for i in range(len(main_indexes)):
        if i == end_point:
            search_df = df.loc[main_indexes[i] :]
            print(search_df.loc[main_indexes[i]][search_df.columns[0]])
            # print(
            #     search_df.loc[main_indexes[i]][search_df.columns[0]],
            #     "|",
            #     str(account),
            #     "|",
            #     str(code),
            # )
        else:
            search_df = df.loc[main_indexes[i] : main_indexes[i + 1]]
            call = {
                "iris_nominal_code": search_df.loc[main_indexes[i]][
                    search_df.columns[0]
                ].split()[2],
                "iris_nominal_name": " ".join(
                    search_df.loc[main_indexes[i]][search_df.columns[0]].split()[3:]
                ),
                "related_xero_nominals": [],
            }
            for k in search_df[search_df.columns[1]]:
                if len(tb[tb["iris"] == k]) != 0:
                    # print(k,str(tb[tb['iris'] == k]['Account']),str(tb[tb['iris'] == k]['Account Code']))
                    account = " ".join(
                        str(tb[tb["iris"] == k]["Account"]).split("\n")[0].split()[1:]
                    )
                    try:
                        code = (
                            str(tb[tb["iris"] == k]["Account Code"])
                            .split("\n")[0]
                            .split()[1]
                        )
                    except Exception as e:
                        code = None
                    print(
                        search_df.loc[main_indexes[i]][search_df.columns[0]].split()[2],
                        "|",
                        " ".join(
                            search_df.loc[main_indexes[i]][
                                search_df.columns[0]
                            ].split()[3:]
                        ),
                        "|",
                        str(account),
                        "|",
                        str(code),
                    )

                    iris_codes.append(
                        search_df.loc[main_indexes[i]][search_df.columns[0]].split()[2]
                    )
                    iris_names.append(
                        " ".join(
                            search_df.loc[main_indexes[i]][
                                search_df.columns[0]
                            ].split()[3:]
                        )
                    )
                    xero_names.append(str(account))
                    xero_codes.append(str(code))

                    call["related_xero_nominals"].append(
                        {
                            "xero_nominal_name": str(account),
                            "xero_nominal_code": str(code),
                            "xero_data": {},
                            "ai_summary": "",
                        }
                    )
            searching_dict["iris_nominals"].append(call)

    # Mapped Dataframe
    mp_df = pd.DataFrame(
        {
            "iris_codes": iris_codes,
            "iris_names": iris_names,
            "xero_names": xero_names,
            "xero_codes": xero_codes,
            "ai_summary": None,
        }
    )
    return searching_dict, mp_df


def xero_iris_mapper(NL_PATH, TB_PATH, TRANS_PATH):
    iris_dict, map_df = make_iris_dict(NL_PATH, TB_PATH)
    dicts = make_xero_mapping(transactions_path=TRANS_PATH, trial_balance_path=TB_PATH)
    for i in iris_dict.keys():
        for j in iris_dict[i]:
            for k in j["related_xero_nominals"]:
                # k['xero_data'] = dicts[k['xero_nominal_name']]
                pass
    return iris_dict, map_df


from helpers.data_processors import process_trial_balance, make_stable
import json
import pandas as pd
