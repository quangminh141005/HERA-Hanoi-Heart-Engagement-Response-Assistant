from app.ai.routing.model_assessor import _bounded_slots
from app.schemas.structured import (
    ScheduleEntryRecord,
    ScheduleLookupResponse,
)
from app.services.structured import _render_doctor_information


def test_model_cannot_replace_unknown_doctor_name() -> None:
    slots = _bounded_slots(
        {'doctor_query': 'ThS.Bs Nguyễn Thị Minh Hoa'},
        original_message='Thông tin về BS. Không Hề Tồn Tại',
    )

    assert slots['doctor_query'] is None


def test_named_doctor_result_uses_only_matching_roster_record() -> None:
    record = ScheduleEntryRecord(
        schedule_entry_id='SCHEDULE-1', service_date='2026-06-08',
        facility_code='CS2', room_label='Phòng khám số 306',
        unit_label='Dịch vụ khám bệnh theo yêu cầu',
        provider_text='BS.CKII Lê Thị Hoài Thu',
        duty_status='scheduled', assignee_type='named_doctor',
    )
    schedule = ScheduleLookupResponse(
        week_start='2026-06-08', classification='partial_official_snapshot',
        warning='Roster only.', records=[record],
    )

    result = _render_doctor_information('Lê Thị Hoài Thu', schedule, [record])

    assert result.grounded is True
    assert result.structured_record_ids == ('SCHEDULE-1',)
    assert 'BS.CKII Lê Thị Hoài Thu' in result.response
