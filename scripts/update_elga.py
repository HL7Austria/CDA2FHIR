import os
import requests
import base64

HEADERS = { 'PRIVATE-TOKEN' : os.environ['GITLAB_CI_TOKEN'] }
PROJECT_ID = os.environ['GITLAB_ELGA_CDA2FHIR_REPO']
TARGET_BRANCH = os.environ['GITLAB_ELGA_CDA2FHIR_REPO_TARGET_BRANCH']
SOURCE_BRANCH = os.environ['RELEASE_TAG']
RELEASE_DESCRIPTION = os.environ['RELEASE_DESCRIPTION']

print('-------------------------------------------------')
print('PROJECT_ID: ' + PROJECT_ID)
print('-------------------------------------------------')
print('TARGET_BRANCH: ' + TARGET_BRANCH)
print('-------------------------------------------------')
print('SOURCE_BRANCH: ' + SOURCE_BRANCH)
print('-------------------------------------------------')
print('RELEASE_DESCRIPTION: ' + RELEASE_DESCRIPTION)
print('-------------------------------------------------')

def check_response(res):
    try:
        res.raise_for_status()
    except:
        if res.status_code == 401:
            print(' ')
            print('##############################################')
            print('YOU ARE NOT AUTHORIZED TO ACCESS THE PROJECT\'S GITLAB-API. CHECK YOUR CI-TOKEN! IT MIGHT HAVE EXPIRED.')
            print('##############################################')
            print(' ')
        print(' ')    
        print(' ')
        print("ERROR: " + res.text)
        print(' ')    
        print(' ')
        # res.raise_for_status()

def retrieve_current_malac_version():
    package = "malac-hd"
    url = f"https://pypi.org/pypi/{package}/json"

    version = requests.get(url).json()["info"]["version"]
    print('MaLaC-HD version: ' + version)
    return version

def create_action(file_path, content, action='update', encoding='text'):
    return {
        'action': action,
        'file_path': file_path,
        'encoding': encoding,
        'content': content
    }

# create new branch based on TARGET_BRANCH
res = requests.post(f'https://gitlab.com/api/v4/projects/{PROJECT_ID}/repository/branches?branch={SOURCE_BRANCH}&ref={TARGET_BRANCH}', headers=HEADERS)
check_response(res)

# create new commit
commit = { 'branch': SOURCE_BRANCH,
           'commit_message': 'Release new mapping',
           'actions': []}
commit_actions = commit['actions']

# update README.md
with open('README.md', 'rb') as binary_file:
    binary_file_data = binary_file.read()
    base64_encoded_data = base64.b64encode(binary_file_data) 
    base64_output = base64_encoded_data.decode('utf-8')
    commit_actions.append(create_action('README.md', base64_output, encoding='base64'))
    
# update malac-hd version
commit_actions.append(create_action('requirements.txt', f'malac-hd[cda]=={retrieve_current_malac_version()}'))
    
res = requests.post(f'https://gitlab.com/api/v4/projects/{PROJECT_ID}/repository/commits', headers=HEADERS, json=commit)
check_response(res)

# create MR
res = requests.post(f'https://gitlab.com/api/v4/projects/{PROJECT_ID}/merge_requests?source_branch={SOURCE_BRANCH}&target_branch={TARGET_BRANCH}&title=Release {SOURCE_BRANCH}&description={RELEASE_DESCRIPTION}', headers=HEADERS)
check_response(res)

