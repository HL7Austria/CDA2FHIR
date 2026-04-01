import os
import glob
import subprocess
import json

INPUT_DIR = "input"
COVERAGE_DIR = "coverage"
OUTPUT_DIR = "output"

with open(os.path.join(INPUT_DIR, 'config.json'), 'r') as file:
    config_json = json.load(file)

for config in config_json:
    directory = config['directory']

    os.makedirs(os.path.join(COVERAGE_DIR, directory), exist_ok=True)

    for filepath in glob.glob(os.path.join(INPUT_DIR, directory, "*.xml")):
        basename = os.path.splitext(os.path.basename(filepath))[0]

        xml_proc = subprocess.Popen([
            "coverage", "run",
            "--source=python-maps",
            f"--data-file={COVERAGE_DIR}/{directory}/.coverage.xml.{basename}",
            "--branch",
            "python-maps/CdaToFhirBundle.4.py",
            "-s", filepath,
            "-t", f"{OUTPUT_DIR}/{directory}/{basename}.fhir.xml"
        ])

        json_proc = subprocess.Popen([
            "coverage", "run",
            "--source=python-maps",
            f"--data-file={COVERAGE_DIR}/{directory}/.coverage.json.{basename}",
            "--branch",
            "python-maps/CdaToFhirBundle.4.py",
            "-s", filepath,
            "-t", f"{OUTPUT_DIR}/{directory}/{basename}.fhir.json"
        ])

        xml_proc.wait()
        json_proc.wait()