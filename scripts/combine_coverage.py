import os
import glob
import subprocess
import json
import urllib.request

INPUT_DIR = "input"
COVERAGE_DIR = "coverage"



with open(os.path.join(INPUT_DIR, 'config.json'), 'r') as file:
    config_json = json.load(file)

for config in config_json:
    directory = config['directory']
    ig_url = config['ig']

    # Coverage XML
    # coverage combine --keep --data-file=coverage/.coverage coverage/
    subprocess.run([
        "coverage", "combine",
        "--keep",
        f"--data-file={COVERAGE_DIR}/{directory}/.coverage",
        f"{COVERAGE_DIR}/{directory}"
    ], check=False)

    # coverage xml --data-file=coverage/.coverage -o coverage/coverage.xml
    subprocess.run([
        "coverage", "xml",
        f"--data-file={COVERAGE_DIR}/{directory}/.coverage",
        "-o", f"{COVERAGE_DIR}/{directory}/coverage.xml"
    ], check=False)

    os.makedirs(os.path.join(COVERAGE_DIR, directory, 'html'), exist_ok=True)

    # coverage html --data-file=coverage/.coverage
    subprocess.run([
        "coverage", "html",
        f"--data-file={COVERAGE_DIR}/{directory}/.coverage",
        "-o", f"{COVERAGE_DIR}/{directory}/html"
    ], check=False)