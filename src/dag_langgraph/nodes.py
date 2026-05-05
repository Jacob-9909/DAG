"""사전 정의된 노드 카탈로그 — 주문 처리 파이프라인.

DAG 의존 관계:
    validate_order
        ├── check_inventory    (재고 확인, 결제 검증과 무관 → 병렬 가능)
        │       └── reserve_inventory
        └── verify_payment     (결제 검증, 재고 확인과 무관 → 병렬 가능)
                └── charge_payment
                        ↓
                  (reserve + charge 둘 다 완료 후)
                  create_shipment
                        ├── send_notification   (병렬 가능)
                        └── update_analytics    (병렬 가능)

선택적 노드:
    apply_discount  — verify_payment 앞에 끼워넣어 할인 금액 계산
    validate_address — create_shipment 앞에 주소 검증
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# State: 노드 간 공유되는 데이터 저장소. 각 노드는 여기서 읽고 새 키만 돌려준다.
State = dict[str, Any]


# frozen=True: 한 번 생성된 Node 객체는 수정 불가 → 레지스트리를 불변으로 유지
@dataclass(frozen=True)
class Node:
    name: str                    # 레지스트리 키이자 Planner가 참조하는 식별자
    description: str             # LLM이 읽고 "이 노드를 언제 써야 하는지" 판단하는 설명
    fn: Callable[[State], State] # 실제 실행 함수. state를 받아 새 키들만 담은 dict 반환


# ---------- 노드 함수 ----------
# 규칙: 각 함수는 자신이 필요한 state 키만 읽고, 자신이 생성한 키만 반환한다.
# 다른 노드의 존재를 알 필요 없다. 연결(엣지)은 Planner가 결정한다.

def _validate_order(state: State) -> State:
    """주문 필수 필드(order_id, items, payment_method, customer_email) 존재 여부 검사."""
    required = {"order_id", "items", "payment_method", "customer_email"}
    # 집합 차집합으로 누락 필드를 한 번에 구한다
    missing = required - state.keys()
    return {
        "order_valid": len(missing) == 0,
        "validation_errors": list(missing),
    }


def _check_inventory(state: State) -> State:
    """items 목록의 각 SKU 재고를 조회. validate_order 이후 실행."""
    items: list[dict] = state.get("items", [])
    # 실제 서비스라면 DB/API 호출. 여기서는 항상 재고 100개로 가정(stub)
    stock: dict[str, int] = {item["sku"]: 100 for item in items}
    # 재고가 0개 이하인 SKU만 추려 품절 목록 생성
    short = [sku for sku, qty in stock.items() if qty < 1]
    return {
        "stock_levels": stock,
        "inventory_ok": len(short) == 0,
        "out_of_stock": short,
    }


def _verify_payment(state: State) -> State:
    """payment_method 유효성 + 한도 검증. validate_order 이후 실행."""
    method: str = state.get("payment_method", "")
    # 허용된 결제 수단만 통과. check_inventory와 의존 관계 없어 병렬 실행 가능
    valid = method in {"card", "transfer", "point"}
    return {
        "payment_valid": valid,
        "payment_error": "" if valid else f"지원하지 않는 결제 수단: {method}",
    }


def _apply_discount(state: State) -> State:
    """coupon_code 기반 할인 금액 계산. verify_payment 이전에 실행 권장."""
    code: str | None = state.get("coupon_code")
    discount_map = {"SAVE10": 0.10, "SAVE20": 0.20, "VIP": 0.30}
    # 쿠폰이 없거나 목록에 없으면 할인율 0
    rate = discount_map.get(code or "", 0.0)
    items: list[dict] = state.get("items", [])
    subtotal = sum(item.get("price", 0) * item.get("qty", 1) for item in items)
    return {
        "discount_rate": rate,
        "discount_amount": round(subtotal * rate, 2),
    }


def _validate_address(state: State) -> State:
    """shipping_address 필드의 필수 키(city, zip, street) 존재 여부 검사."""
    addr: dict = state.get("shipping_address", {})
    required = {"city", "zip", "street"}
    missing = required - addr.keys()
    return {
        "address_valid": len(missing) == 0,
        "address_errors": list(missing),
    }


def _reserve_inventory(state: State) -> State:
    """check_inventory 통과 후 재고 선점 예약. inventory_ok=True 필요."""
    # inventory_ok가 False면 예약 없이 실패 결과만 반환
    if not state.get("inventory_ok"):
        return {"reservation_id": None, "reservation_ok": False}
    # uuid로 고유한 예약 ID 생성
    return {
        "reservation_id": f"RSV-{uuid.uuid4().hex[:8].upper()}",
        "reservation_ok": True,
    }


def _charge_payment(state: State) -> State:
    """verify_payment 통과 후 실제 결제 실행. payment_valid=True 필요."""
    # payment_valid가 False면 결제 없이 실패 결과만 반환
    if not state.get("payment_valid"):
        return {"charge_id": None, "charge_ok": False}
    # apply_discount가 선행됐으면 discount_amount가 state에 있음. 없으면 0
    discount = state.get("discount_amount", 0.0)
    items: list[dict] = state.get("items", [])
    subtotal = sum(item.get("price", 0) * item.get("qty", 1) for item in items)
    charged = round(subtotal - discount, 2)
    return {
        "charge_id": f"CHG-{uuid.uuid4().hex[:8].upper()}",
        "charge_ok": True,
        "charged_amount": charged,
    }


def _create_shipment(state: State) -> State:
    """reserve_inventory + charge_payment 완료 후 배송 생성."""
    # fan-in 노드: 두 선행 노드(재고 예약, 결제)가 모두 성공해야 배송 생성 가능
    if not state.get("reservation_ok") or not state.get("charge_ok"):
        return {"shipment_id": None, "shipment_ok": False}
    return {
        "shipment_id": f"SHP-{uuid.uuid4().hex[:8].upper()}",
        "shipment_ok": True,
        "tracking_url": f"https://track.example.com/{state.get('order_id', 'unknown')}",
    }


def _send_notification(state: State) -> State:
    """배송 생성 완료 후 고객 이메일 발송. create_shipment 이후 실행."""
    email = state.get("customer_email", "")
    shipment_id = state.get("shipment_id", "")
    # 이메일 주소와 배송 ID가 모두 있을 때만 발송 성공으로 표시
    return {
        "notification_sent": bool(email and shipment_id),
        "notified_to": email,
    }


def _update_analytics(state: State) -> State:
    """배송 생성 완료 후 주문 통계 업데이트. send_notification 과 병렬 가능."""
    # send_notification과 의존 관계가 없으므로 동시에 실행해도 된다
    return {
        "analytics_updated": True,
        "recorded_order_id": state.get("order_id"),
        "recorded_amount": state.get("charged_amount", 0.0),
    }


# ---------- 레지스트리 ----------
# description 문자열이 Planner의 판단 근거가 된다.
# "requires:", "writes:" 형식으로 의존 관계와 출력 키를 명시해야
# LLM이 올바른 엣지를 결정할 수 있다.

_REGISTRY: list[Node] = [
    Node(
        name="validate_order",
        description=(
            "주문 필수 필드(order_id·items·payment_method·customer_email) 검증. "
            "writes: order_valid, validation_errors. 항상 첫 번째로 실행."
        ),
        fn=_validate_order,
    ),
    Node(
        name="check_inventory",
        description=(
            "state['items'][*].sku 재고 조회. "
            "writes: stock_levels, inventory_ok, out_of_stock. "
            "requires: validate_order."
        ),
        fn=_check_inventory,
    ),
    Node(
        name="verify_payment",
        description=(
            "state['payment_method'] 유효성·한도 검증. "
            "writes: payment_valid, payment_error. "
            "requires: validate_order. check_inventory 와 병렬 실행 가능."
        ),
        fn=_verify_payment,
    ),
    Node(
        name="apply_discount",
        description=(
            "state['coupon_code'] 기반 할인 계산. "
            "writes: discount_rate, discount_amount. "
            "requires: validate_order. verify_payment 앞에 실행."
        ),
        fn=_apply_discount,
    ),
    Node(
        name="validate_address",
        description=(
            "state['shipping_address'] 필수 키(city·zip·street) 검증. "
            "writes: address_valid, address_errors. "
            "requires: validate_order. create_shipment 앞에 실행."
        ),
        fn=_validate_address,
    ),
    Node(
        name="reserve_inventory",
        description=(
            "재고 선점 예약. "
            "writes: reservation_id, reservation_ok. "
            "requires: check_inventory (inventory_ok=True)."
        ),
        fn=_reserve_inventory,
    ),
    Node(
        name="charge_payment",
        description=(
            "실제 결제 실행. discount_amount 있으면 차감. "
            "writes: charge_id, charge_ok, charged_amount. "
            "requires: verify_payment (payment_valid=True). apply_discount 선행 권장."
        ),
        fn=_charge_payment,
    ),
    Node(
        name="create_shipment",
        description=(
            "배송 생성 및 운송장 발급. "
            "writes: shipment_id, shipment_ok, tracking_url. "
            "requires: reserve_inventory AND charge_payment 둘 다 완료."
        ),
        fn=_create_shipment,
    ),
    Node(
        name="send_notification",
        description=(
            "고객 이메일 발송(배송 확인·운송장). "
            "writes: notification_sent, notified_to. "
            "requires: create_shipment. update_analytics 와 병렬 실행 가능."
        ),
        fn=_send_notification,
    ),
    Node(
        name="update_analytics",
        description=(
            "주문 통계 DB 업데이트(금액·주문ID). "
            "writes: analytics_updated, recorded_order_id, recorded_amount. "
            "requires: create_shipment. send_notification 과 병렬 실행 가능."
        ),
        fn=_update_analytics,
    ),
]

# 이름으로 노드를 빠르게 조회하기 위한 딕셔너리
NODES: dict[str, Node] = {n.name: n for n in _REGISTRY}


def descriptions() -> list[dict[str, str]]:
    """Planner 프롬프트에 주입할 카탈로그. LLM은 이 설명만 보고 노드를 선택·연결한다."""
    return [{"name": n.name, "description": n.description} for n in _REGISTRY]
