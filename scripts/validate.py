import os
import subprocess
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

parser = argparse.ArgumentParser()
parser.add_argument("--directory", required=True)
parser.add_argument("--basename", required=True)
parser.add_argument("--fmt", required=True, choices=["xml", "json"])
args = parser.parse_args()

directory = args.directory
basename = args.basename
fmt = args.fmt
INPUT_DIR = "input"
OUTPUT_DIR = "output"
VALIDATION_DIR = "validation"

os.makedirs(os.path.join(VALIDATION_DIR, directory), exist_ok=True)

cmd = [
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

logging.info(f"Validating {directory}/{basename} as {fmt.upper()} ...")

with open(f"{VALIDATION_DIR}/{directory}/{basename}.val.{fmt}.log", "w") as log:
    proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)

if proc.returncode != 0:
    logging.error(f"Validation errors in FHIR {fmt.upper()}: {basename}")
    raise SystemExit(proc.returncode)