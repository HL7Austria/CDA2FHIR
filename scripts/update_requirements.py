import requests
import os

def retrieve_current_malac_version():
    package = "malac-hd"
    url = f"https://pypi.org/pypi/{package}/json"

    version = requests.get(url).json()["info"]["version"]
    print('MaLaC-HD version: ' + version)
    return version

with open(os.path.join('python-maps', 'requirements.txt'), 'w') as file:
    file.write(f'malac-hd[cda]=={retrieve_current_malac_version()}')