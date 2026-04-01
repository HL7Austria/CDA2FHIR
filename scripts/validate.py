import os
import subprocess
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

parser = argparse.ArgumentParser()
parser.add_argument("--directory", required=True)
parser.add_argument("--basename", required=True)
args = parser.parse_args()

directory = args.directory
basename = args.basename
INPUT_DIR = "input"
OUTPUT_DIR = "output"
VALIDATION_DIR = "validation"

os.makedirs(os.path.join(VALIDATION_DIR, directory), exist_ok=True)

def validator_cmd(fmt):
    return [
        "java", "-jar", "validator_cli.jar",
        f"{OUTPUT_DIR}/{directory}/{basename}.fhir.{fmt}",
        "-locale", "de-AT",
        "-version", "4.0",
        "-ig", f"igs/{directory}_package.tgz",
        "-html-output", f"{VALIDATION_DIR}/{directory}/{basename}.val.{fmt}.html",
        "-show-message-ids",
        "-allow-example-urls", "true",
        "-advisor-file", f"{INPUT_DIR}/{directory}/advisor.json",
        "-extension", "any",
        "-display-issues-are-warnings"
    ]

logging.info(f"Validating {directory}/{basename} ...")

xml_log  = open(f"{VALIDATION_DIR}/{directory}/{basename}.val.xml.log",  "w")
json_log = open(f"{VALIDATION_DIR}/{directory}/{basename}.val.json.log", "w")

xml_proc  = subprocess.run(validator_cmd("xml"),  stdout=xml_log,  stderr=subprocess.STDOUT)
json_proc = subprocess.run(validator_cmd("json"), stdout=json_log, stderr=subprocess.STDOUT)


xml_log.close()
json_log.close()

if xml_proc.returncode != 0:
    logging.error(f"Validation errors in FHIR XML: {basename}")
if json_proc.returncode != 0:
    logging.error(f"Validation errors in FHIR JSON: {basename}")