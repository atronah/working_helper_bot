import os
import sys

if sys.version_info >= (3, 8):
    from importlib.metadata import metadata
else:
    from importlib_metadata import metadata


def main():
    service_name = sys.argv[1] if len(sys.argv) > 1 else 'work_assistant_bot'
    service_dir = '/etc/systemd/system'
    service_ext = '.service'
    
    service_path = os.path.join(service_dir, service_name + service_ext)
    
    if os.path.exists(service_path):
        print(f'{service_path} already exists')
        sys.exit(1)
    
    package_info = metadata('work_assistant')
    working_directory = os.path.abspath('.')
    
    with open(service_path, 'w') as srvc:
        srvc.write(os.linesep.join([
            "[Unit]",
            f"Description={package_info['Summary']}",
        
            "[Service]",
            f"User={package_info['Name']}",
            f"WorkingDirectory={working_directory}",
            f"ExecStart=/usr/bin/env bash -c 'cd {working_directory}/ && source venv/bin/activate && work_assistant_bot'",
            "Restart=always",
            "",
            "[Install]",
            "WantedBy=multi-user.target"]))