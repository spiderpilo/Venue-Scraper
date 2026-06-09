import json
import pandas as pd
# import os
# import sys

JSON_BATCH_SOURCE = 'data/processed/json_batches_combined_presplit.json'

def output_model_venue() -> list:
    try: 
        with open(JSON_BATCH_SOURCE, 'r') as file:
            model_venue = json.load(file)
        print(json.dumps(model_venue, indent=4))
    except FileNotFoundError:
        print("Error: The json file was not found.")
    return model_venue

def json_conv_csv(json_obj:list, target_col:list) -> pd.DataFrame:
    if len(target_col) == 0:
        print("ERROR: List of Column Names NOT Provided")
        return None
    data_list = []
    data_dict = {}
    for col in target_col:
        for element in json_obj:
            data_list.append(element[col])
        data_dict[col] = data_list
        data_list = []
    df = pd.DataFrame.from_dict(data_dict)
    return df 

