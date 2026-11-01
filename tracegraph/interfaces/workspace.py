from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from pathlib import Path


class IWorkspace(ABC):
    """
    #Feature: Source workspace
    #Scenario: Contract for locating repositories and materialising a commit as a directory
    #Complexity: Time O(1) - constant per call excluding git work
    """

    @abstractmethod
    def local_path(self, url: str) -> Path:
        """
        #Feature: Source workspace
        #Scenario: Resolve a file:// URL or absolute path to an existing directory
        #Complexity: Time O(1) - constant
        """

    @abstractmethod
    def resolve_ref(self, path: Path, ref: str) -> str:
        """
        #Feature: Source workspace
        #Scenario: Resolve a git ref (or WORKTREE) to the commit id stamped on the snapshot
        #Complexity: Time O(1) - one git call
        """

    @abstractmethod
    def checkout(self, path: Path, commit_sha: str) -> AbstractContextManager[Path]:
        """
        #Feature: Source workspace
        #Scenario: Context manager yielding a directory containing the files of commit_sha
        #Complexity: Time O(f) - linear in repository size
        """
