"""CLI entrypoint: `flow-gen <goal>`."""
from __future__ import annotations

import argparse
import json
import logging
import sys

from flow_gen.executor import build
from flow_gen.nodes import descriptions
from flow_gen.planner import plan as make_plan


def main() -> None:
    parser = argparse.ArgumentParser(prog="flow-gen", description="Dynamic DAG runner")
    parser.add_argument("goal", nargs="*", help="user goal (natural language)")
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

    goal = " ".join(args.goal) or "서울 날씨 조회 후 영어로 요약"
    sys.stdout.write(f"[goal] {goal}\n\n")

    p = make_plan(goal)
    sys.stdout.write(f"[thought] {p.thought}\n")
    sys.stdout.write(f"[initial_state] {json.dumps(p.initial_state, ensure_ascii=False)}\n")
    sys.stdout.write(f"[selected] {p.selected}\n")
    sys.stdout.write("[planner edges]\n")
    for src, dst in p.edges:
        sys.stdout.write(f"  {src} -> {dst}\n")

    g = build(p)
    sys.stdout.write("[graph edges (+ START/END)]\n")
    for src, dst in sorted(g.edges):
        sys.stdout.write(f"  {src} -> {dst}\n")

    compiled = g.compile()
    sys.stdout.write(f"\n[topo order] {' -> '.join(compiled.order)}\n\n")

    final = compiled.invoke(initial_state=p.initial_state, verbose=args.verbose)
    sys.stdout.write("[final state]\n")
    sys.stdout.write(json.dumps(final, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
