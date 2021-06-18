import os
import sys

if sys.version_info >= (3, 8):
    from importlib.metadata import metadata
else:
    from importlib_metadata import metadata


def main():
    package_info = metadata('work_assistant')
    working_directory = os.path.abspath('.')
    with open('work_assistant_bot.service', 'w') as srvc:
        srvc.write(os.linesep.join([
            "[Unit]",
            f"Description={package_info['Summary']}",
        
            "[Service]",
            f"User={package_info['Name']}",
            f"WorkingDirectory={working_directory}",
            "ExecStart=/usr/bin/env bash -c 'cd {working_directory}/ && source venv/bin/activate && work_assistant bot'",
            "Restart=always",
            "",
            "[Install]",
            "WantedBy=multi-user.target"]))