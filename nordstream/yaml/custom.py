import logging
from nordstream.utils.log import logger
from nordstream.yaml.generator import YamlGeneratorBase


class CustomGenerator(YamlGeneratorBase):
    def loadFile(self, file):
        logger.verbose("Loading YAML file.")
        with open(file, "r") as templateFile:
            try:
                self._defaultTemplate = templateFile.read()

            except Exception as exception:
                logger.error("[+] Error while reading yaml file")
                logger.exception(exception)

    def writeFile(self, file):
        logger.verbose("Writing YAML file.")
        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug("Current yaml file:")
            self.displayYaml()

        with open(file, "w") as outputFile:
            outputFile.write(self._defaultTemplate)

    def displayYaml(self):
        logger.raw(self._defaultTemplate, logging.INFO)
