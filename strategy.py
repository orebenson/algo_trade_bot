import json
import os
import keys

strategy_dir = keys.strategies_dir

def load_strategy(strategy_name):
    with open(strategy_dir + strategy_name + '.json') as json_file:
        data = json.load(json_file)
        return data
