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

    os.makedirs(os.path.join(OUTPUT_DIR, directory), exist_ok=True)
    os.makedirs(os.path.join(COVERAGE_DIR, directory), exist_ok=True)
    os.makedirs(os.path.join(VALIDATION_DIR, directory), exist_ok=True)

    urllib.request.urlretrieve(ig_url, directory + '_package.tgz')

    for filepath in glob.glob(os.path.join(INPUT_DIR, directory, "*.xml")):
        basename = os.path.splitext(os.path.basename(filepath))[0]

        # Coverage XML
        subprocess.run([
            "coverage", "run",
            "--source=python-maps",
            f"--data-file={COVERAGE_DIR}/{directory}/.coverage.xml.{basename}",
            "--branch",
            "python-maps/CdaToFhirBundle.4.py",
            "-s", filepath,
            "-t", f"{OUTPUT_DIR}/{directory}/{basename}.fhir.xml"
        ], check=False)

        # Coverage JSON
        subprocess.run([
            "coverage", "run",
            "--source=python-maps",
            f"--data-file={COVERAGE_DIR}/{directory}/.coverage.json.{basename}",
            "--branch",
            "python-maps/CdaToFhirBundle.4.py",
            "-s", filepath,
            "-t", f"{OUTPUT_DIR}/{directory}/{basename}.fhir.json"
        ], check=False)

        # Validate XML
        with open(f"{VALIDATION_DIR}/{directory}/{basename}.val.xml.log", "w") as log_file:
            result = subprocess.run([
                "java", "-jar", "validator_cli.jar",
                f"{OUTPUT_DIR}/{directory}/{basename}.fhir.xml",
                "-locale", "de-AT",
                "-version", "4.0",
                "-ig", f"{directory}_package.tgz",
                "-html-output", f"{VALIDATION_DIR}/{directory}/{basename}.val.xml.html",
                "-show-message-ids",
                "-allow-example-urls", "true",
                "-advisor-file", f"{INPUT_DIR}/{directory}/advisor.json",
                "-extension", "any",
                "-display-issues-are-warnings"
            ], stdout=log_file, stderr=subprocess.STDOUT)

            if result.returncode != 0:
                print("validation errors in FHIR XML")

        # Validate JSON
        with open(f"{VALIDATION_DIR}/{directory}/{basename}.val.json.log", "w") as log_file:
            result = subprocess.run([
                "java", "-jar", "validator_cli.jar",
                f"{OUTPUT_DIR}/{directory}/{basename}.fhir.json",
                "-locale", "de-AT",
                "-version", "4.0",
                "-ig", f"{directory}_package.tgz",
                "-html-output", f"{VALIDATION_DIR}/{directory}/{basename}.val.json.html",
                "-show-message-ids",
                "-allow-example-urls", "true",
                "-advisor-file", f"{INPUT_DIR}/{directory}/advisor.json",
                "-extension", "any",
                "-display-issues-are-warnings"
            ], stdout=log_file, stderr=subprocess.STDOUT)

            if result.returncode != 0:
                print("validation errors in FHIR JSON")