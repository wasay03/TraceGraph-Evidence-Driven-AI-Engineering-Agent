from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status

from tracegraph.constants.permissions import agent
from tracegraph.containers import ServiceContainer
from tracegraph.dependencies import get_service_container, require_permission
from tracegraph.schemas.runs import ApprovalRequest, ClarifyRequest, RunCreateRequest, RunResponse

router = APIRouter(prefix="/runs", tags=["runs"])


def _schedule(request: Request, tasks: BackgroundTasks, run_id: int) -> None:
    """
    #Feature: Runs API
    #Scenario: Execute the run after the response is sent, on the app-scoped executor
    #Complexity: Time O(1) - constant
    """
    tasks.add_task(request.app.state.agent_executor.execute, run_id)


@router.post("", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(require_permission(agent.execute))])
async def start_run(body: RunCreateRequest, request: Request, tasks: BackgroundTasks,
                    services: ServiceContainer = Depends(get_service_container)) -> RunResponse:
    """
    #Feature: Runs API
    #Scenario: POST /runs - create a run (interactive or benchmark mode, ablation config) and start it
    #Complexity: Time O(1) - constant

    Args:
        body: Repo, request text, mode and config.
        request: Incoming request (app-scoped executor).
        tasks: Background task queue.
        services: Per-request service container.

    Returns:
        The queued run.
    """
    run = await services.agent.start(body)
    _schedule(request, tasks, run.id)
    return run


@router.get("/{run_id}", response_model=RunResponse, dependencies=[Depends(require_permission(agent.read))])
async def get_run(run_id: int, events_after: int = Query(0, ge=0),
                  services: ServiceContainer = Depends(get_service_container)) -> RunResponse:
    """
    #Feature: Runs API
    #Scenario: GET /runs/{id} - state, phase, artifacts, verification and audit events
    #Complexity: Time O(l) - events page
    """
    return await services.agent.get(run_id, events_after)


@router.post("/{run_id}/approval", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(require_permission(agent.approve))])
async def approve_run(run_id: int, body: ApprovalRequest, request: Request, tasks: BackgroundTasks,
                      services: ServiceContainer = Depends(get_service_container)) -> RunResponse:
    """
    #Feature: Runs API
    #Scenario: POST /runs/{id}/approval - approve, edit or reject the plan; approved runs resume
    #Complexity: Time O(1) - constant
    """
    run = await services.agent.approve(run_id, body)
    _schedule(request, tasks, run_id)
    return run


@router.post("/{run_id}/clarify", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(require_permission(agent.execute))])
async def clarify_run(run_id: int, body: ClarifyRequest, request: Request, tasks: BackgroundTasks,
                      services: ServiceContainer = Depends(get_service_container)) -> RunResponse:
    """
    #Feature: Runs API
    #Scenario: POST /runs/{id}/clarify - answer an ambiguity question and resume
    #Complexity: Time O(1) - constant
    """
    run = await services.agent.clarify(run_id, body)
    _schedule(request, tasks, run_id)
    return run
