import os
import glob
import subprocess
import json
import logging

INPUT_DIR = "input"
OUTPUT_DIR = "output"

with open(os.path.join(INPUT_DIR, 'config.json'), 'r') as file:
    config_json = json.load(file)

for config in config_json:
    directory = config['directory']

    os.makedirs(os.path.join(OUTPUT_DIR, directory), exist_ok=True)

    for filepath in glob.glob(os.path.join(INPUT_DIR, directory, "*.xml")):
        basename = os.path.splitext(os.path.basename(filepath))[0]

        xml_proc = subprocess.Popen([
            "python", "python-maps/CdaToFhirBundle.4.py",
            "-s", filepath,
            "-t", f"{OUTPUT_DIR}/{directory}/{basename}.fhir.xml"
        ])

        json_proc = subprocess.Popen([
            "python", "python-maps/CdaToFhirBundle.4.py",
            "-s", filepath,
            "-t", f"{OUTPUT_DIR}/{directory}/{basename}.fhir.json"
        ])

        xml_proc.wait()
        json_proc.wait()

        if xml_proc.returncode != 0:
            logging.error(f"XML conversion failed for {basename} (exit {xml_proc.returncode})")
        if json_proc.returncode != 0:
            logging.error(f"JSON conversion failed for {basename} (exit {json_proc.returncode})")

        logging.info(f"Done {basename}")