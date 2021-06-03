#! /usr/bin/env bash

script_path="$( cd "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"

pkill -f "python3 ${script_path}/bot.py"

pushd "${script_path}"

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source ./venv/bin/activate
pip install --upgrade pip setuptools
pip install .
# full path to prevent killing any other bots with `bot.py` main script
nohup python3 "${script_path}/bot.py" &

popd