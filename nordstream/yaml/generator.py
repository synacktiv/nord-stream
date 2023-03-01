import yaml
import logging
from nordstream.utils.log import logger


class YamlGeneratorBase:
    _defaultTemplate = ""

    @property
    def defaultTemplate(self):
        return self._defaultTemplate

    @defaultTemplate.setter
    def defaultTemplate(self, value):
        logger.warning("Using your own yaml template might break stuff.")
        self._defaultTemplate = value

    @staticmethod
    def getEnvironnmentFromYaml(yamlFile):
        with open(yamlFile, "r") as file:
            try:
                data = yaml.safe_load(file)
                return data.get("jobs").get("init").get("environment", None)

            except yaml.YAMLError as exception:
                logger.exception("Yaml error")
                logger.exception(exception)

    def loadFile(self, file):
        logger.verbose("Loading YAML file.")
        with open(file, "r") as templateFile:
            try:
                self._defaultTemplate = yaml.load(templateFile, Loader=yaml.BaseLoader)

            except yaml.YAMLError as exception:
                logger.error("[+] Yaml error")
                logger.exception(exception)

    def writeFile(self, file):
        logger.verbose("Writing YAML file.")
        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug("Current yaml file:")
            self.displayYaml()

        with open(file, "w") as outputFile:
            yaml.dump(self._defaultTemplate, outputFile, sort_keys=False)

    def displayYaml(self):
        logger.raw(yaml.dump(self._defaultTemplate, sort_keys=False), logging.INFO)
