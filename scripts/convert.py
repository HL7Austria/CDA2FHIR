import os
import glob
import subprocess
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

INPUT_DIR = "input"
OUTPUT_DIR = "output"

with open(os.path.join(INPUT_DIR, 'config.json'), 'r') as file:
    config_json = json.load(file)

# collect all processes before waiting on any
procs = []

for config in config_json:
    directory = config['directory']
    os.makedirs(os.path.join(OUTPUT_DIR, directory), exist_ok=True)

    for filepath in glob.glob(os.path.join(INPUT_DIR, directory, "*.xml")):
        basename = os.path.splitext(os.path.basename(filepath))[0]

        logging.info(f"Launching {directory}/{basename} ...")

        xml_proc = subprocess.Popen([
            "python", "python-maps/CdaToFhirBundle.4.py",
            "-s", filepath,
            "-t", os.path.join(OUTPUT_DIR, directory, f"{basename}.fhir.xml")
        ])

        json_proc = subprocess.Popen([
            "python", "python-maps/CdaToFhirBundle.4.py",
            "-s", filepath,
            "-t", os.path.join(OUTPUT_DIR, directory, f"{basename}.fhir.json")
        ])

        procs.append((directory, basename, "xml", xml_proc))
        procs.append((directory, basename, "json", json_proc))

# now wait for all of them
for directory, basename, fmt, proc in procs:
    proc.wait()
    if proc.returncode != 0:
        logging.error(f"{fmt.upper()} conversion failed for {directory}/{basename} (exit {proc.returncode})")
    else:
        logging.info(f"Done {fmt.upper()} {directory}/{basename}")