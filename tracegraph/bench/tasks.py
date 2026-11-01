from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Gold(BaseModel):
    """
    #Feature: Benchmark (PRD 12.2)
    #Scenario: Hand-labelled ground truth: what breaks, what is affected, what is guarded, required obligations,
               nodes where a correct system must say UNKNOWN, and the files a reference fix touches
    #Complexity: Time O(1) - constant
    """

    model_config = ConfigDict(extra="forbid")

    breaks: list[str] = Field(default_factory=list)
    at_risk: list[str] = Field(default_factory=list)
    guarded: list[str] = Field(default_factory=list)
    obligations: list[str] = Field(default_factory=list)
    unknown_expected: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)

    @property
    def affected(self) -> set[str]:
        """
        #Feature: Benchmark
        #Scenario: Everything the change truly affects (BREAKS or AT_RISK)
        #Complexity: Time O(g) - gold size
        """
        return set(self.breaks) | set(self.at_risk)


class Task(BaseModel):
    """
    #Feature: Benchmark
    #Scenario: One benchmark task on a repository: request text, ChangeSpecs and gold sets
    #Complexity: Time O(1) - constant
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    repo: str = Field(description="Repository directory, relative to the suite file")
    kind: Literal["change", "question"] = "change"
    request: str
    changes: list[dict[str, Any]] = Field(min_length=1)
    tokens: list[str] = Field(min_length=1, description="Search terms a text-only baseline would use")
    gold: Gold
    hidden_tests: list[str] = Field(default_factory=list)
    hole_task: bool = False
    notes: str = ""


class Suite(BaseModel):
    """
    #Feature: Benchmark
    #Scenario: Frozen set of tasks; tasks added after freezing are reported separately (PRD 12.4)
    #Complexity: Time O(1) - constant
    """

    name: str
    frozen: bool = False
    tasks: list[Task]
    base_dir: Path = Path(".")


def load_suite(path: Path) -> Suite:
    """
    #Feature: Benchmark
    #Scenario: Load a suite YAML; repo paths resolve relative to the suite file
    #Complexity: Time O(s) - file size

    Raises:
        ValueError: When the file is missing or invalid.
    """
    if path is None or not path.is_file():
        raise ValueError(f"[load_suite] Suite file {path} does not exist.")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Suite(**data, base_dir=path.parent.resolve())
