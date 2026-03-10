import os
import requests
import base64

HEADERS = { 'PRIVATE-TOKEN' : os.environ['GLE_GITLAB_CI_TOKEN'] }
PROJECT_ID = os.environ['GITLAB_ELGA_CDA2FHIR_REPO']
TARGET_BRANCH = os.environ['GITLAB_ELGA_CDA2FHIR_REPO_TARGET_BRANCH']
SOURCE_BRANCH = 'test-02'

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

# create new branch based on TARGET_BRANCH
res = requests.post(f'https://gitlab.com/api/v4/projects/{PROJECT_ID}/repository/branches?branch=test-01&ref={TARGET_BRANCH}', headers=HEADERS)
check_response(res)

# create new commit
commit = { 'branch': SOURCE_BRANCH,
           'commit_message': 'Release new mapping',
           'actions': []}
commit_actions = commit['actions']

with open('README.md', 'rb') as binary_file:
    binary_file_data = binary_file.read()
    base64_encoded_data = base64.b64encode(binary_file_data) 
    base64_output = base64_encoded_data.decode('utf-8')
    commit_actions.append({
        'action': 'update',
        'file_path': 'README.md',
        'encoding': 'base64',
        'content': base64_output})
    
res = requests.post(f'https://gitlab.com/api/v4/projects/{PROJECT_ID}/repository/commits', headers=HEADERS, json=commit)
check_response(res)

# create MR
res = requests.post(f'https://gitlab.com/api/v4/projects/{PROJECT_ID}/merge_requests?source_branch={SOURCE_BRANCH}&target_branch={TARGET_BRANCH}&title=Release&description=asdf aasdf asdf asdf', headers=HEADERS, json=commit)
check_response(res)

