import asyncio

from pydantic import Field

from tracegraph.constants import agent as a
from tracegraph.errors import Errors
from tracegraph.sandbox.run_sandbox import SandboxWorkspace, safe_relative
from tracegraph.tools.common import ToolInput
from tracegraph.tools.registry import ToolContext, ToolOutput, ToolSpec

_EXPLORE = frozenset({a.PHASE_DISCOVER, a.PHASE_ANALYZE, a.PHASE_PLAN, a.PHASE_IMPLEMENT})
_IMPLEMENT = frozenset({a.PHASE_IMPLEMENT})
_SEARCH = frozenset({a.PHASE_DISCOVER, a.PHASE_ANALYZE, a.PHASE_IMPLEMENT})


class PathInput(ToolInput):
    """
    #Feature: Tool catalog (workspace)
    #Scenario: Repository-relative directory
    #Complexity: Time O(1) - constant
    """

    path: str = "."


class GrepInput(ToolInput):
    """
    #Feature: Tool catalog (workspace)
    #Scenario: Fixed-string search
    #Complexity: Time O(1) - constant
    """

    pattern: str = Field(min_length=2, max_length=200)


class ReadInput(ToolInput):
    """
    #Feature: Tool catalog (workspace)
    #Scenario: File line range
    #Complexity: Time O(1) - constant
    """

    path: str = Field(min_length=1)
    start: int = Field(default=1, ge=1)
    end: int | None = Field(default=None, ge=1)


class PatchInput(ToolInput):
    """
    #Feature: Tool catalog (workspace)
    #Scenario: Unified diff relative to the repository root (a/ b/ prefixes accepted)
    #Complexity: Time O(1) - constant
    """

    diff: str = Field(min_length=10)
    step_id: str | None = None


class PatchIdInput(ToolInput):
    """
    #Feature: Tool catalog (workspace)
    #Scenario: Patch to revert
    #Complexity: Time O(1) - constant
    """

    patch_id: str = Field(pattern=r"^p[0-9a-f]{8}$")


class TestsInput(ToolInput):
    """
    #Feature: Tool catalog (execution)
    #Scenario: pytest node ids (empty runs the whole suite)
    #Complexity: Time O(1) - constant
    """

    tests: list[str] = Field(default_factory=list, max_length=50)


class FilesInput(ToolInput):
    """
    #Feature: Tool catalog (execution)
    #Scenario: Files to lint
    #Complexity: Time O(1) - constant
    """

    files: list[str] = Field(min_length=1, max_length=50)


def _sandbox(ctx: ToolContext) -> SandboxWorkspace:
    """
    #Feature: Tool catalog (workspace)
    #Scenario: The run's sandbox; workspace tools need one
    #Complexity: Time O(1) - constant

    Raises:
        Errors.HTTP.BadRequest: When the run has no sandbox.
    """
    if ctx.sandbox is None:
        raise Errors.HTTP.BadRequest("This run has no sandbox worktree.")
    return ctx.sandbox


def _in_scope(ctx: ToolContext, paths: list[str]) -> None:
    """
    #Feature: Scope gating (PRD 9.3)
    #Scenario: In implement, files must belong to the approved plan's scope set
    #Complexity: Time O(p) - paths

    Raises:
        Errors.HTTP.Forbidden: ScopeViolation naming the files outside scope.
    """
    if ctx.phase != a.PHASE_IMPLEMENT:
        return
    outside = sorted(p for p in (safe_relative(p) for p in paths) if p not in ctx.scope_files)
    if outside:
        raise Errors.HTTP.Forbidden(f"ScopeViolation: {outside} are outside the approved scope "
                                    f"{sorted(ctx.scope_files)}; amend the plan to widen it.")


async def list_dir(ctx: ToolContext, args: PathInput) -> ToolOutput:
    """
    #Feature: Tool catalog (baseline)
    #Scenario: Directory listing
    #Complexity: Time O(d) - entries
    """
    return ToolOutput("\n".join(await asyncio.to_thread(_sandbox(ctx).list_dir, args.path)) or "(empty)")


async def grep_repo(ctx: ToolContext, args: GrepInput) -> ToolOutput:
    """
    #Feature: Tool catalog (baseline)
    #Scenario: Fixed-string search over Python files
    #Complexity: Time O(b) - bytes scanned
    """
    return ToolOutput(await asyncio.to_thread(_sandbox(ctx).grep, args.pattern) or "no matches")


async def read_file(ctx: ToolContext, args: ReadInput) -> ToolOutput:
    """
    #Feature: Tool catalog (workspace)
    #Scenario: Numbered file lines from the sandbox; scope-gated during implement
    #Complexity: Time O(l) - lines
    """
    _in_scope(ctx, [args.path])
    end = args.end or args.start + 400
    return ToolOutput(await asyncio.to_thread(_sandbox(ctx).read_file, args.path, args.start, end))


async def apply_patch(ctx: ToolContext, args: PatchInput) -> ToolOutput:
    """
    #Feature: Tool catalog (workspace)
    #Scenario: Apply a unified diff inside the scope set; the patch is recorded on the run
    #Complexity: Time O(d) - diff size
    """
    sandbox = _sandbox(ctx)
    _in_scope(ctx, SandboxWorkspace.patch_files(args.diff))
    patch_id, files = await asyncio.to_thread(sandbox.apply_patch, args.diff)
    ctx.state.patches.append({"patch_id": patch_id, "files": files, "step_id": args.step_id, "diff": args.diff})
    return ToolOutput(f"applied {patch_id} to {files}")


async def revert_patch(ctx: ToolContext, args: PatchIdInput) -> ToolOutput:
    """
    #Feature: Tool catalog (workspace)
    #Scenario: Reverse an applied patch
    #Complexity: Time O(d) - diff size
    """
    await asyncio.to_thread(_sandbox(ctx).revert_patch, args.patch_id)
    ctx.state.patches = [p for p in ctx.state.patches if p["patch_id"] != args.patch_id]
    return ToolOutput(f"reverted {args.patch_id}")


async def run_tests(ctx: ToolContext, args: TestsInput) -> ToolOutput:
    """
    #Feature: Tool catalog (execution)
    #Scenario: pytest in the sandbox with a fixed command template
    #Complexity: Time O(test runtime)
    """
    result = await asyncio.to_thread(_sandbox(ctx).run_tests, args.tests)
    return ToolOutput(f"ok={result['ok']} counts={result['counts']}\n{result['output'][-2500:]}")


async def run_checks(ctx: ToolContext, args: FilesInput) -> ToolOutput:
    """
    #Feature: Tool catalog (execution)
    #Scenario: Lint changed files when a linter is installed
    #Complexity: Time O(f) - files
    """
    result = await asyncio.to_thread(_sandbox(ctx).run_checks, args.files)
    return ToolOutput(f"{result['status']} ok={result['ok']}\n{result['output'][-2500:]}")


WORKSPACE_TOOLS: list[ToolSpec] = [
    ToolSpec("list_dir", "1.0.0", a.GROUP_BASELINE, a.SIDE_READ, _SEARCH, PathInput, list_dir, "List a directory."),
    ToolSpec("grep_repo", "1.0.0", a.GROUP_BASELINE, a.SIDE_READ, _SEARCH, GrepInput, grep_repo,
             "Fixed-string search over Python files, returns file:line:text."),
    ToolSpec("read_file", "1.0.0", a.GROUP_BASELINE, a.SIDE_READ, _EXPLORE, ReadInput, read_file,
             "Read numbered lines of a file. During implement only files in the approved scope.", scoped=True),
    ToolSpec("apply_patch", "1.0.0", a.GROUP_BASELINE, a.SIDE_SANDBOX_WRITE, _IMPLEMENT, PatchInput, apply_patch,
             "Apply a unified diff (paths relative to the repository root) inside the approved scope.", scoped=True),
    ToolSpec("revert_patch", "1.0.0", a.GROUP_BASELINE, a.SIDE_SANDBOX_WRITE, _IMPLEMENT, PatchIdInput, revert_patch,
             "Revert a previously applied patch."),
    ToolSpec("run_tests", "1.0.0", a.GROUP_BASELINE, a.SIDE_EXEC, _IMPLEMENT, TestsInput, run_tests,
             "Run pytest node ids in the sandbox (all tests when empty)."),
    ToolSpec("run_checks", "1.0.0", a.GROUP_BASELINE, a.SIDE_EXEC, _IMPLEMENT, FilesInput, run_checks,
             "Lint files in the sandbox."),
]
