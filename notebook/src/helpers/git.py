import logging
import os
import subprocess

log = logging.getLogger()


class Git:
    """
    Git helper. Allows one to more easily interface with Git.

    Attributes
    ----------
    file: str
        File we wish to interface with inside a git repo
    directory: str
        The git repo directory
    """

    def __init__(self, file: str):
        self.file = file
        self.directory = os.path.dirname(file)

    def _run_on_dir(self, command: str) -> str:
        """
        Helper to run a git command. Moves to git dir to run and moves back
        when done.

        Args:
            command (str): Git command to run

        Returns:
            str: Git command output
        """
        log.debug(f"Running git command {command}")
        cwd = os.getcwd()
        os.chdir(self.directory)
        try:
            output = subprocess.run(command, shell=True, check=True,
                                    encoding="utf-8",
                                    stdout=subprocess.PIPE)
        finally:
            os.chdir(cwd)
        return output.stdout

    def pull(self):
        """ Reload git file with pull """
        log.info("Reloading git for source file")
        self._run_on_dir("git pull --rebase")

    def get_hash_from_version(self, versions_back: int) -> str:
        """ Get hash of the change file versions_back iterations """
        log.info("Getting hash for source file")
        if type(versions_back) != int or versions_back <= 0:
            raise ValueError(
                f"Expecting positive number, instead got {versions_back}")
        return self._run_on_dir(f"git rev-parse HEAD~{versions_back}")

    def get_previous(self, versions_back: int = 1) -> (str, str):
        """ Pull locally a version of the file versions_back iterations """
        log.info("Getting previous version of file")
        if type(versions_back) != int or versions_back <= 0:
            raise ValueError(
                f"Expecting positive number, instead got {versions_back}")
        self._run_on_dir(f"git show HEAD~{versions_back}:./{os.path.basename(self.file)} > /tmp/.ini{versions_back}")
        log.debug(f"Writing file /tmp/.ini{versions_back}")
        return f"/tmp/.ini{versions_back}", self.get_hash_from_version(versions_back).strip()
