import os
import glob
import subprocess
import json
import urllib.request

INPUT_DIR = "input"
OUTPUT_DIR = "output"
COVERAGE_DIR = "coverage"
VALIDATION_DIR = "validation"

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
        f"--data-file=coverage/{directory}/.coverage",
        f"coverage/{directory}"
    ], check=False)

    # coverage xml --data-file=coverage/.coverage -o coverage/coverage.xml
    subprocess.run([
        "coverage", "xml",
        f"--data-file=coverage/{directory}/.coverage",
        "-o", f"coverage/{directory}/coverage.xml"
    ], check=False)

    # coverage html --data-file=coverage/.coverage
    subprocess.run([
        "coverage", "html",
        f"--data-file=coverage/{directory}/.coverage"
    ], check=False)