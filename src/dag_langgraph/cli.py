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

    # --list-nodes: 노드 카탈로그를 JSON으로 출력하고 종료
    if args.list_nodes:
        sys.stdout.write(json.dumps(descriptions(), ensure_ascii=False, indent=2) + "\n")
        return

    # goal 인자가 없으면 기본 시나리오 실행
    goal = " ".join(args.goal) or "주문 처리해줘"
    sys.stdout.write(f"[goal] {goal}\n\n")

    # 1단계: Planner → Plan (LLM 또는 stub)
    p = make_plan(goal)
    sys.stdout.write(f"[thought] {p.thought}\n")
    sys.stdout.write(f"[initial_state] {json.dumps(p.initial_state, ensure_ascii=False)}\n")
    sys.stdout.write(f"[selected nodes] {p.selected}\n\n")

    # 2단계: Planner가 결정한 엣지 출력
    sys.stdout.write("[planner edges]\n")
    for src, dst in p.edges:
        sys.stdout.write(f"  {src} → {dst}\n")

    # 3단계: 실행 단계 출력 (병렬 가능 여부 표시)
    sys.stdout.write("\n[execution steps]\n")
    for step in p.steps:
        # 이 step의 task 목록이 parallel 그룹 중 하나에 전부 포함되면 병렬 표시
        parallel_marker = ""
        for group in p.parallel:
            if all(t in group for t in step.tasks) and len(step.tasks) > 1:
                parallel_marker = "  ← 병렬"
                break
        sys.stdout.write(f"  {step.id}: {step.goal}{parallel_marker}\n")
        for task in step.tasks:
            sys.stdout.write(f"    · {task}\n")

    # 4단계: executor가 START/END를 붙인 최종 그래프 엣지 출력
    g = build(p)
    sys.stdout.write("\n[graph edges (+ START/END)]\n")
    for src, dst in sorted(g.edges):
        sys.stdout.write(f"  {src} → {dst}\n")

    # 5단계: 위상 정렬 순서 출력 (실제 실행 순서)
    compiled = g.compile()
    sys.stdout.write(f"\n[topo order]\n  {' → '.join(compiled.order)}\n\n")

    # 6단계: 그래프 실행 → 최종 state에서 주요 키만 출력
    final = compiled.invoke(initial_state=p.initial_state, verbose=args.verbose)
    sys.stdout.write("[result]\n")
    # 출력할 키 순서를 고정해 결과를 읽기 쉽게 정렬
    result_keys = [
        "order_valid", "inventory_ok", "payment_valid",
        "discount_amount", "reservation_id", "charge_id", "charged_amount",
        "shipment_id", "shipment_ok", "tracking_url",
        "notification_sent", "analytics_updated",
    ]
    for key in result_keys:
        if key in final:  # Plan에 따라 없는 키도 있으므로 존재 여부 확인
            sys.stdout.write(f"  {key}: {final[key]}\n")


if __name__ == "__main__":
    main()
