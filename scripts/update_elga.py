import os
import requests
import base64
import re
import pandas
import glob

HEADERS = { 'PRIVATE-TOKEN' : os.environ['GITLAB_CI_TOKEN'] }
PROJECT_ID = os.environ['GITLAB_ELGA_CDA2FHIR_REPO']
TARGET_BRANCH = os.environ['GITLAB_ELGA_CDA2FHIR_REPO_TARGET_BRANCH']
RELEASE_URL = os.environ['RELEASE_URL']
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
with open(os.path.join('python-maps', 'README.md'), 'rb') as binary_file:
    binary_file_data = binary_file.read()
    base64_encoded_data = base64.b64encode(binary_file_data) 
    base64_output = base64_encoded_data.decode('utf-8')
    commit_actions.append(create_action('README.md', base64_output, encoding='base64'))

# update CdaToFhirBundle.py
with open(os.path.join('python-maps', 'CdaToFhirBundle.4.py'), 'rb') as binary_file:
    binary_file_data = binary_file.read()
    base64_encoded_data = base64.b64encode(binary_file_data) 
    base64_output = base64_encoded_data.decode('utf-8')
    commit_actions.append(create_action('CdaToFhirBundle.4.py', base64_output, encoding='base64'))
    
# update requirements.txt
with open(os.path.join('python-maps', 'requirements.txt'), 'rb') as binary_file:
    binary_file_data = binary_file.read()
    base64_encoded_data = base64.b64encode(binary_file_data) 
    base64_output = base64_encoded_data.decode('utf-8')
    commit_actions.append(create_action('requirements.txt', base64_output, encoding='base64'))

data = {
    'Metadata': [os.environ['RELEASE_URL'], os.environ['RELEASE_TAG'], os.environ['RELEASE_DATE']]
}
index = ['RELEASE_URL', 'RELEASE_TAG', 'RELEASE_DATE']
df = pandas.DataFrame(data, index = index)

for excel in glob.glob(os.path.join('python-maps', 'documentation', '*.xlsx')):
    print(excel)

    with pandas.ExcelWriter(excel, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
        df.to_excel(writer, sheet_name='META', header=False)

    with open(excel, 'rb') as binary_file:
        binary_file_data = binary_file.read()
        base64_encoded_data = base64.b64encode(binary_file_data) 
        base64_output = base64_encoded_data.decode('utf-8')
        commit_actions.append(create_action(os.path.join('documentation', os.path.basename(excel)), base64_output, encoding='base64'))
    
res = requests.post(f'https://gitlab.com/api/v4/projects/{PROJECT_ID}/repository/commits', headers=HEADERS, json=commit)
check_response(res)

# create MR

# replace all "@<username>" occurences as they might link to wrong users in GitLab
updated_release_description = re.sub(r'@', '', RELEASE_DESCRIPTION)
# add link to original GitHub release
updated_release_description = f'**Link to GitHub-Release:** {RELEASE_URL}\n{updated_release_description}' 

data = {
    'title': f'Release {SOURCE_BRANCH}',
    'source_branch': SOURCE_BRANCH,
    'target_branch': TARGET_BRANCH,
    'description': updated_release_description
}
res = requests.post(f'https://gitlab.com/api/v4/projects/{PROJECT_ID}/merge_requests', headers=HEADERS, json=data)
check_response(res)
