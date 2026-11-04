"""
CLI entry point for the AI Workflow Platform.

Usage:
    python -m app.cli "your natural language query" [--user-id USER] [--budget TOKENS] [--cost-limit USD]

Example:
    python -m app.cli "Review the deployment plan for security impact." --user-id demo-user
"""

from __future__ import annotations

import argparse
import asyncio
import uuid


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Workflow Platform — governed AI task execution",
    )
    parser.add_argument(
        "query",
        nargs="+",
        help="Natural language task description",
    )
    parser.add_argument(
        "--user-id",
        default="demo-user",
        help="User ID for the workflow (default: demo-user)",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=10000,
        help="Token budget (default: 10000)",
    )
    parser.add_argument(
        "--cost-limit",
        type=float,
        default=5.0,
        help="Cost limit in USD (default: 5.0)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted text",
    )
    return parser.parse_args()


async def run_workflow(
    query: str,
    user_id: str,
    token_budget: int,
    cost_limit: float,
) -> int:
    """Create and execute a workflow, streaming progress to stdout."""
    from app.models.workflow import WorkflowRun
    from app.core.database import SessionLocal
    from app.workflows.runner import execute_workflow

    task_id = str(uuid.uuid4())

    # Create workflow record
    workflow = WorkflowRun(
        id=task_id,
        user_id=user_id,
        input_query=query,
        token_budget=token_budget,
        cost_budget_usd=cost_limit,
    )

    async with SessionLocal() as session:
        session.add(workflow)
        await session.commit()
        await session.refresh(workflow)

    print(f"Workflow created: {task_id}")
    print(f"Query: {query}")
    print(f"User: {user_id} | Budget: {token_budget} tokens | Limit: ${cost_limit:.2f}")
    print("-" * 60)

    # Execute
    async with SessionLocal() as session:
        run = await execute_workflow(session, task_id)
        await session.refresh(run)

        print("\nResult:")
        print(f"  Status:       {run.current_status}")
        print(f"  Risk Level:   {run.risk_level}")
        print(f"  Current Step: {run.current_step}")
        if run.risk_factors:
            print("  Risk Factors:")
            for factor in run.risk_factors:
                print(f"    - {factor}")
        if run.final_response:
            print(f"\n  Response:\n    {run.final_response[:500]}")
        if run.error_info:
            print(f"\n  Error: {run.error_info}")
        print(f"\n  Tokens Used:  {run.total_tokens_used}")
        print(f"  Cost:         ${run.cost_usd:.6f}")
        print(f"  Retries:      {run.retry_count}")

    if run.current_status == "completed":
        return 0
    return 1


def main() -> int:
    args = parse_args()
    query = " ".join(args.query)

    return asyncio.run(
        run_workflow(
            query=query,
            user_id=args.user_id,
            token_budget=args.budget,
            cost_limit=args.cost_limit,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
