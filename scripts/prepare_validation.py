import json
import os
import glob
import urllib.request
import tarfile

INPUT_DIR = "input"
OUTPUT_DIR = "output"
IG_DIR = "igs"

os.makedirs(IG_DIR, exist_ok=True)

with open(os.path.join(INPUT_DIR, 'config.json'), 'r') as f:
    config_json = json.load(f)

matrix_entries = []

for config in config_json:
    directory = config['directory']
    ig_url = config['ig']

    # Download IG once into shared igs/ folder
    ig_filename = os.path.join(IG_DIR, f"{directory}_package.tgz")
    urllib.request.urlretrieve(ig_url, ig_filename)

    if 'manualDependencies' in config:
        for dep in config['manualDependencies']:
            package_dir = os.path.join(os.path.expanduser('~'), '.fhir', 'packages', dep['package'])
            os.makedirs(package_dir, exist_ok=True)
            package_file = os.path.join(package_dir, 'package.tgz')
            urllib.request.urlretrieve(dep['url'], package_file)
            with tarfile.open(package_file, "r:gz") as tar:
                tar.extractall(path=package_dir)

    for filepath in glob.glob(os.path.join(OUTPUT_DIR, directory, "*.fhir.xml")):
        basename = os.path.splitext(os.path.splitext(os.path.basename(filepath))[0])[0]
        for fmt in ["xml", "json"]:
            matrix_entries.append({
                "directory": directory,
                "basename": basename,
                "fmt": fmt
            })

matrix = json.dumps({"include": matrix_entries})
with open(os.environ["GITHUB_OUTPUT"], "a") as f:
    f.write(f"matrix={matrix}\n")