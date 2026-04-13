import os
from pathlib import Path
import subprocess
import json
import shutil

INPUT_DIR = os.path.join('.', 'input')
COVERAGE_DIR = os.path.join('.', 'coverage')

# coverage combine --keep --data-file=coverage/.coverage coverage/
def combine(directory, keep=True):
    data_file = os.path.join(directory, '.coverage')

    command = ["coverage", "combine"]
    if keep:
        command.append("--keep")
    command.append(f"--data-file={data_file}")
    command.append(directory)

    subprocess.run(command, check=False)

# coverage xml --data-file=coverage/.coverage -o coverage/coverage.xml
def xml(directory):
    data_file = os.path.join(directory, '.coverage')
    out_file = os.path.join(directory, 'coverage.xml')

    subprocess.run(["coverage", "xml", f"--data-file={data_file}", "-o", out_file], check=False)

# coverage html --data-file=coverage/.coverage
def html(directory, target_dir='html'):
    data_file = os.path.join(directory, '.coverage')
    output_dir = os.path.join(directory, target_dir)
    os.makedirs(output_dir, exist_ok=True)

    subprocess.run(["coverage", "html", "-d", output_dir, f"--data-file={data_file}"], check=False)

with open(os.path.join(INPUT_DIR, 'config.json'), 'r') as file:
    config_json = json.load(file)

# create coverage per input directory (i.e. document type)
for config in config_json:
    directory = os.path.join(COVERAGE_DIR, config['directory'])
    ig_url = config['ig']

    # copy coverage files to COVERAGE_DIR for overall coverage generation
    for file in Path(directory).glob('.coverage*'):
        shutil.copy(file, os.path.join('.', COVERAGE_DIR))

    # combine coverages
    combine(directory)

    # HTML coverage
    html(directory)

# create overall coverage
# combine all coverages
combine(COVERAGE_DIR, keep=False)

# create xml coverage for display in pull requests
xml(COVERAGE_DIR)

# create html coverage
html(COVERAGE_DIR, target_dir='overall_html_cov')
