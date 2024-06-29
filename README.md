# Algo Bot

## Description
A simplistic algorithmic trading bot.

## Features
- dynamic strategy application using json
- backtest strategies using historical data

## Setup

0. Install and setup MetaTrader5 desktop client

1. Create a `keys.py` file and configure it with your account number, password, server, and strategies directory.

```python
# keys.py

account_num = "your_account_number"
password = "your_password"
server = "your_server"
strategies_dir = "path_to_your_strategies_directory"
```

2. Create a virtual environment using the following command:

```bash
python -m venv .venv
```

3. Download TA-Lib from [https://pypi.org/project/TA-Lib/](https://pypi.org/project/TA-Lib/) and extract it to `C:\ta-lib`.

4. Activate the virtual environment:

```bash
.venv\Scripts\activate  # For Windows
```

or

```bash
source .venv/bin/activate  # For Linux/Mac
```

5. Install required packages using the following command:

```bash
pip install -r requirements.txt
```

6. Run the trader:

```bash
python trader.py <strategy_name>
```
