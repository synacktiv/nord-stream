import copy
from nordstream.utils.log import logger
from nordstream.yaml.generator import YamlGeneratorBase


class CircleCIPipelineGenerator(YamlGeneratorBase):
    # Default secret-extraction pipeline template.
    # The command is built dynamically from the list of variable names to extract.
    # CircleCI does NOT support $VAR interpolation in environment: blocks — project
    # env vars are already present in the shell, so we print them directly by name.
    # This constant is never mutated; instances receive a deep copy in __init__.
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
        # Deep-copy the class-level constant so mutations on this instance
        # never bleed into other instances or the class itself.
        self._defaultTemplate = copy.deepcopy(CircleCIPipelineGenerator._DEFAULT_TEMPLATE)

    def generatePipelineForSecretsExtraction(self, projectVars, contexts=None):
        """Populate the template with the vars to extract and optional context names."""
        self._buildExtractionCommand(projectVars or [])
        if contexts:
            self.addContextsToYaml(contexts)

    def _buildExtractionCommand(self, varNames):
        """
        Build a shell command that prints each named variable as NAME=VALUE,
        then double-base64-encodes the result.

        CircleCI does not support $VAR interpolation in environment: blocks.
        Project env vars and context env vars are already available in the job's
        shell environment — we reference them directly with printf/printenv.
        """
        if not varNames:
            self._defaultTemplate["jobs"]["init"]["steps"][0]["run"]["command"] = (
                "echo 'no secrets configured' | base64 -w0 | base64 -w0"
            )
            return

        # Build: printf '%s\n' "VAR1=$VAR1" "VAR2=$VAR2" ... | base64 -w0 | base64 -w0
        # Using printf with double-quoted args so the shell expands $VAR at runtime.
        pairs = " ".join(f'"secret_{v}=${v}"' for v in varNames)
        command = f"printf '%s\\n' {pairs} | base64 -w0 | base64 -w0"
        self._defaultTemplate["jobs"]["init"]["steps"][0]["run"]["command"] = command

    def addContextsToYaml(self, contexts):
        """
        Attach a list of context names to the workflow job entry.
        Transforms the bare string "init" into {"init": {"context": [...]}}.
        """
        self._defaultTemplate["workflows"]["main"]["jobs"][0] = {
            "init": {"context": list(contexts)}
        }
