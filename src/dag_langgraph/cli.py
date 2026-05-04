"""CLI entrypoint: `flow-gen <goal>`."""
from __future__ import annotations

import argparse
import json
import logging
import sys

from dag_langgraph.executor import build
from dag_langgraph.nodes import descriptions
from dag_langgraph.planner import plan as make_plan


def main() -> None:
    parser = argparse.ArgumentParser(prog="flow-gen", description="Dynamic DAG order pipeline runner")
    parser.add_argument("goal", nargs="*", help="처리 목표 (자연어)")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--list-nodes", action="store_true", help="노드 카탈로그 출력")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.list_nodes:
        sys.stdout.write(json.dumps(descriptions(), ensure_ascii=False, indent=2) + "\n")
        return

    goal = " ".join(args.goal) or "주문 처리해줘"
    sys.stdout.write(f"[goal] {goal}\n\n")

    p = make_plan(goal)
    sys.stdout.write(f"[thought] {p.thought}\n")
    sys.stdout.write(f"[initial_state] {json.dumps(p.initial_state, ensure_ascii=False)}\n")
    sys.stdout.write(f"[selected nodes] {p.selected}\n\n")

    sys.stdout.write("[planner edges]\n")
    for src, dst in p.edges:
        sys.stdout.write(f"  {src} → {dst}\n")

    sys.stdout.write("\n[execution steps]\n")
    for step in p.steps:
        parallel_marker = ""
        for group in p.parallel:
            if all(t in group for t in step.tasks) and len(step.tasks) > 1:
                parallel_marker = "  ← 병렬"
                break
        sys.stdout.write(f"  {step.id}: {step.goal}{parallel_marker}\n")
        for task in step.tasks:
            sys.stdout.write(f"    · {task}\n")

    g = build(p)
    sys.stdout.write("\n[graph edges (+ START/END)]\n")
    for src, dst in sorted(g.edges):
        sys.stdout.write(f"  {src} → {dst}\n")

    compiled = g.compile()
    sys.stdout.write(f"\n[topo order]\n  {' → '.join(compiled.order)}\n\n")

    final = compiled.invoke(initial_state=p.initial_state, verbose=args.verbose)

    sys.stdout.write("[result]\n")
    result_keys = [
        "order_valid", "inventory_ok", "payment_valid",
        "discount_amount", "reservation_id", "charge_id", "charged_amount",
        "shipment_id", "shipment_ok", "tracking_url",
        "notification_sent", "analytics_updated",
    ]
    for key in result_keys:
        if key in final:
            sys.stdout.write(f"  {key}: {final[key]}\n")


if __name__ == "__main__":
    main()
