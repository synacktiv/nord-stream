import subprocess
from nordstream.utils.log import logger

"""
TODO: find an alternative to subprocess it's a bit crappy.
"""

"""
Return True if the command succeeds (returns 0), else return False.
"""

ATTACK_COMMIT_MSG = "Deployment"
CLEAN_COMMIT_MSG = "Remove deployment"


class Git:

    _user = "nord-stream"
    _email = "nord-stream@localhost.com"
    _keyId = None

    @property
    def email(self):
        return self._email

    @email.setter
    def email(self, email):
        self._email = email

    @property
    def user(self):
        return self._user

    @user.setter
    def user(self, user):
        self._user = user

    @property
    def keyId(self):
        return self._keyId

    @keyId.setter
    def keyId(self, keyId):
        self._keyId = keyId

    def gitRunCommand(self, command):
        try:
            # debug level
            if logger.level <= 10:
                logger.debug(f"Running: {command}")
                subprocess.run(command, shell=True, check=True)
            else:
                subprocess.run(command, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            return False
        return True

    def gitInitialization(self, branch, branchAlreadyExists=False):
        logger.verbose("Git init")

        self.gitRunCommand(f"git config user.Name {self._user}")
        self.gitRunCommand(f"git config user.email {self._email}")

        if self._keyId != None:
            self.gitRunCommand(f"git config user.signingkey {self._keyId}")
            self.gitRunCommand(f"git config commit.gpgsign true")

        if branchAlreadyExists:
            self.gitRunCommand(f"git checkout {branch}")
            return

        self.gitRunCommand(f"git checkout --orphan {branch}")
        self.gitRunCommand(f"git pull origin {branch}")
        self.gitRunCommand("git rm . -rf")

    def gitCleanRemote(self, branch, leaveOneFile=False):
        logger.verbose("Cleaning remote branch")
        self.gitRunCommand("git rm . -rf")
        self.gitRunCommand("git rm .github/ -rf")

        if leaveOneFile:
            self.gitRunCommand(f"touch test_dev.txt")
            self.gitRunCommand(f"git add -A")

        self.gitRunCommand(f"git commit -m '{CLEAN_COMMIT_MSG}'")

        if leaveOneFile:
            self.gitRunCommand(f"git push origin {branch}")
        else:
            self.gitRunCommand(f"git push -d origin {branch}")

    def gitRemoteBranchExists(self, branch):
        logger.verbose("Checking if remote branch exists")
        return self.gitRunCommand(f"git ls-remote --exit-code origin {branch}")

    def gitUndoLastPushedCommits(self, branch, pushedCommitsCount):
        for _ in range(pushedCommitsCount):
            self.gitRunCommand("git reset --hard HEAD~")

        if pushedCommitsCount and not self.gitRunCommand(f"git push -f origin {branch}"):
            logger.warning(
                "Could not delete commit(s) pushed by the tool using hard reset and force push. Trying to revert commits."
            )

            self.gitRunCommand("git pull")
            self.gitRunCommand(f"git revert --no-commit HEAD~{pushedCommitsCount}..")

            self.gitRunCommand(f"git commit -m '{CLEAN_COMMIT_MSG}'")
            if pushedCommitsCount and not self.gitRunCommand(f"git push origin {branch}"):
                logger.error("Error while trying to revert changes !")

    def gitDeleteRemote(self, branch):
        logger.verbose("Git delete remote.")
        return subprocess.Popen(
            f"git push -d origin {branch}",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def gitPush(self, branch):
        logger.verbose("Pushing to remote branch")
        self.gitRunCommand("git add .")
        self.gitRunCommand(f"git commit -m '{ATTACK_COMMIT_MSG}'")
        return subprocess.Popen(
            f"git push origin {branch}",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def gitCreateEmptyFile(self, file):
        self.gitRunCommand(f"touch {file}")

    def gitMvFile(self, src, dest):
        self.gitRunCommand(f"mv {src} {dest}")

    def gitCpFile(self, src, dest):
        self.gitRunCommand(f"cp {src} {dest}")

    def gitCreateDir(self, directory):
        self.gitRunCommand(f"mkdir -p {directory}")

    def gitClone(self, url):
        self.gitRunCommand(f"git clone {url}")

    def gitGetCurrentBranch(self):
        return (
            subprocess.Popen(
                "git rev-parse --abbrev-ref HEAD | tr -d '\n'",
                shell=True,
                stdout=subprocess.PIPE,
            )
            .communicate()[0]
            .decode("UTF-8")
        )

    # not needed anymore
    def gitIsGloalUserConfigured(self):
        res = subprocess.Popen(
            "git config --global user.Name",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        res.wait()
        if res.returncode != 0:
            return False

        return True

    # not needed anymore
    def gitIsGloalEmailConfigured(self):
        res = subprocess.Popen(
            "git config --global user.email",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        res.wait()
        if res.returncode != 0:
            return False

        return True
