import os
import glob
import subprocess
import json
import urllib.request
import tarfile

INPUT_DIR = "input"
OUTPUT_DIR = "output"
VALIDATION_DIR = "validation"

with open(os.path.join(INPUT_DIR, 'config.json'), 'r') as file:
    config_json = json.load(file)

for config in config_json:
    directory = config['directory']
    ig_url = config['ig']

    os.makedirs(os.path.join(VALIDATION_DIR, directory), exist_ok=True)

    if 'manualDependencies' in config:
        for manual_dependency in config['manualDependencies']:
            package_dir = os.path.join(os.path.expanduser('~'), '.fhir', 'packages', manual_dependency['package'])
            os.makedirs(package_dir, exist_ok=True)
            package_file = os.path.join(package_dir, 'package.tgz')
            urllib.request.urlretrieve(manual_dependency['url'], package_file)
            with tarfile.open(package_file, "r:gz") as tar:
                tar.extractall(path=package_dir)

    urllib.request.urlretrieve(ig_url, directory + '_package.tgz')

    for filepath in glob.glob(os.path.join(OUTPUT_DIR, directory, "*.fhir.xml")):
        basename = filepath.replace(".fhir.xml", "").replace(f"{OUTPUT_DIR}/{directory}/", "")

        def validator_cmd(fmt):
            return [
                "java", "-jar", "validator_cli.jar",
                f"{OUTPUT_DIR}/{directory}/{basename}.fhir.{fmt}",
                "-locale", "de-AT",
                "-version", "4.0",
                "-ig", f"{directory}_package.tgz",
                "-html-output", f"{VALIDATION_DIR}/{directory}/{basename}.val.{fmt}.html",
                "-show-message-ids",
                "-allow-example-urls", "true",
                "-advisor-file", f"{INPUT_DIR}/{directory}/advisor.json",
                "-extension", "any",
                "-display-issues-are-warnings"
            ]

        xml_log  = open(f"{VALIDATION_DIR}/{directory}/{basename}.val.xml.log",  "w")
        json_log = open(f"{VALIDATION_DIR}/{directory}/{basename}.val.json.log", "w")

        xml_proc  = subprocess.Popen(validator_cmd("xml"),  stdout=xml_log,  stderr=subprocess.STDOUT)
        json_proc = subprocess.Popen(validator_cmd("json"), stdout=json_log, stderr=subprocess.STDOUT)

        xml_proc.wait()
        json_proc.wait()

        xml_log.close()
        json_log.close()

        if xml_proc.returncode != 0:
            print(f"Validation errors in FHIR XML: {basename}")
        if json_proc.returncode != 0:
            print(f"Validation errors in FHIR JSON: {basename}")