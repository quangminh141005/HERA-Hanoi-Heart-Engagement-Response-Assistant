'''Repeatable, provider-free smoke test through the public same-origin gateway.'''

from __future__ import annotations

import argparse
import json
import secrets
import urllib.parse
import urllib.request
from typing import Any


def _request(
    base_url: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    method: str | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    body = None
    request_headers = {
        'Accept': 'application/json',
        'X-Request-ID': 'deploy-smoke',
        **(headers or {}),
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        request_headers['Content-Type'] = 'application/json; charset=utf-8'
    request = urllib.request.Request(
        f'{base_url.rstrip("/")}{path}',
        data=body,
        headers=request_headers,
        method=method or ('POST' if payload is not None else 'GET'),
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f'{path} returned HTTP {response.status}')
        return json.load(response)


def _require(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8080')
    args = parser.parse_args()

    health = _request(args.base_url, '/healthz')
    _require(health.get('status') == 'ok', f'Liveness failed: {health}')
    ready = _request(args.base_url, '/readyz')
    _require(
        ready.get('status') == 'ok' and ready.get('structured_bundle_ready'),
        f'Readiness failed: {ready}',
    )
    clock = _request(args.base_url, '/api/v1/runtime-clock')
    _require(
        clock.get('reference_date') and clock.get('last_schedule_date'),
        f'Runtime clock is incomplete: {clock}',
    )

    query = urllib.parse.urlencode({'query': 'khám', 'facility_code': 'CS1'})
    prices = _request(args.base_url, f'/api/v1/service-prices?{query}')
    _require(prices.get('records'), 'Service-price lookup returned no records')
    _require(prices.get('citations'), 'Service-price lookup has no citation')
    missing_query = urllib.parse.urlencode(
        {'query': '__hera_missing_service_smoke__', 'facility_code': 'CS1'}
    )
    missing_price = _request(
        args.base_url,
        f'/api/v1/service-prices?{missing_query}',
    )
    _require(not missing_price.get('records'), 'Unknown service fabricated a price')

    bhyt = _request(args.base_url, '/api/v1/bhyt/household-contributions')
    _require(bhyt.get('tiers') and bhyt.get('citations'), 'BHYT lookup failed')
    schedule_query = urllib.parse.urlencode(
        {'week_start': '2026-07-13', 'facility_code': 'CS2'}
    )
    schedule = _request(args.base_url, f'/api/v1/schedules?{schedule_query}')
    _require(schedule.get('records') and schedule.get('warning'), 'Schedule failed')
    missing_schedule = urllib.parse.urlencode(
        {'week_start': '2099-01-05', 'facility_code': 'CS2'}
    )
    no_schedule = _request(args.base_url, f'/api/v1/schedules?{missing_schedule}')
    _require(not no_schedule.get('records'), 'Unknown week fabricated a schedule')

    emergency = _request(
        args.base_url,
        '/api/v1/chat',
        {'message': 'Tôi đang đau ngực dữ dội và khó thở', 'locale': 'vi-VN'},
    )
    _require(emergency.get('emergency'), 'Emergency handoff failed')

    sessions = _request(args.base_url, '/api/v1/booking-sessions')
    _require(sessions.get('records'), 'No eligible prototype booking session')
    _booking_hold_smoke(args.base_url, sessions['records'])

    print(
        json.dumps(
            {
                'status': 'ok',
                'model_api_calls': 0,
                'checks': [
                    'health_and_readiness',
                    'runtime_clock',
                    'price_hit_and_no_match',
                    'bhyt_tiers',
                    'schedule_hit_and_no_match',
                    'emergency_handoff',
                    'postgres_booking_hold_idempotency_and_release',
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


def _booking_hold_smoke(base_url: str, records: list[dict[str, Any]]) -> None:
    available = next(
        (record for record in records if int(record.get('remaining_count', 0)) > 0),
        None,
    )
    _require(available is not None, 'No booking session has remaining capacity')
    operation = secrets.token_hex(12)
    owner = f'deploy-smoke-{secrets.token_hex(8)}'
    payload = {
        'booking_session_id': available['booking_session_id'],
        'idempotency_key': f'deploy-smoke-{operation}',
        'patient': {
            'full_name': 'Nguyen Van Smoke',
            'phone_number': '0900000000',
            'cccd_number': '001001000000',
            'bhyt_card_number': 'DN40101000000',
        },
    }
    owner_header = {'X-Anonymous-Session-ID': owner}
    first = _request(
        base_url,
        '/api/v1/booking-holds',
        payload,
        headers=owner_header,
    )
    _require(first.get('status') == 'held', 'PostgreSQL hold was not created')
    _require(first.get('hold_token'), 'Booking hold did not return owner token')
    replay = _request(
        base_url,
        '/api/v1/booking-holds',
        payload,
        headers=owner_header,
    )
    _require(replay.get('hold_id') == first.get('hold_id'), 'Idempotency changed hold')
    _require(replay.get('idempotent_replay') is True, 'Replay was not identified')
    released = _request(
        base_url,
        f'/api/v1/booking-holds/{first["hold_id"]}',
        method='DELETE',
        headers={'Authorization': f'Bearer {first["hold_token"]}'},
    )
    _require(released.get('status') == 'released', 'Smoke hold was not released')


if __name__ == '__main__':
    raise SystemExit(main())
