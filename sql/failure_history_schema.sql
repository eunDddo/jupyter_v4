-- Manufacturing failure history database schema and seed data.
-- Usage:
--   sqlite3 agent_data/failure_history.sqlite < sql/failure_history_schema.sql

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS failure_history;

CREATE TABLE IF NOT EXISTS failure_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date TEXT NOT NULL,
    failure_type TEXT NOT NULL,
    component TEXT,
    symptom TEXT,
    root_cause TEXT,
    corrective_action TEXT,
    preventive_action TEXT,
    downtime_min INTEGER DEFAULT 0,
    related_features_json TEXT,
    source_type TEXT DEFAULT 'sample_history',
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_failure_history_date
    ON failure_history(event_date);

CREATE INDEX IF NOT EXISTS idx_failure_history_type
    ON failure_history(failure_type);

CREATE INDEX IF NOT EXISTS idx_failure_history_component
    ON failure_history(component);

INSERT INTO failure_history
    (event_date, failure_type, component, symptom, root_cause,
     corrective_action, preventive_action, downtime_min, related_features_json, source_type, notes)
VALUES
    ('2026-06-20', 'HDF', 'spindle_bearing',
     '스핀들 부하 상승과 베어링 온도 증가',
     '냉각 성능 저하와 베어링 윤활 상태 불량',
     '베어링 온도 추적, 쿨런트 유량 점검, 절삭 조건 완화',
     '고부하 조건에서 온도/진동 추세 모니터링, 윤활 주기 단축',
     55, '{"torque":64,"process_temperature":311,"rotational_speed":1280}', 'sample_history',
     'AI4I HDF/열 방출 관련 사례로 사용'),

    ('2026-06-18', 'TWF', 'tooling',
     '공구 마모 한계 접근, 토크 상승, 채터 의심',
     '공구 마모 누적과 절삭 부하 증가',
     '공구 교체, 스핀들 런아웃 확인, 절삭 조건 완화',
     'tool_wear 기준 초과 전 교체, 고토크 조건 모니터링',
     120, '{"torque":62,"tool_wear":215,"rotational_speed":1320}', 'sample_history',
     'AI4I feature와 연결 가능한 공구 마모 사례'),

    ('2026-06-15', 'OSF', 'spindle_drive',
     '스핀들 부하 상한 접근, 공정온도 상승',
     '마모 공구 사용과 절삭 조건 과부하',
     '공구 상태 확인, 이송/절입 조건 완화, 토크 기준 재확인',
     '공구별 허용 부하 기준 관리, 부하 상승 경향 조기 알림',
     65, '{"torque":60,"tool_wear":198,"process_temperature":309}', 'sample_history',
     'overstrain 위험 사례'),

    ('2026-06-12', 'PWF', 'drive_system',
     '구동부 응답 이상과 순간 전류 상승',
     '전원 품질 불안정과 커넥터 체결 상태 불량',
     '전원 공급 상태 점검, 커넥터 재체결, 드라이브 팬 상태 확인',
     '전원 품질 주기 점검, 전장부 체결 상태 체크리스트화',
     95, '{"rotational_speed":1510,"torque":41}', 'sample_history',
     'power failure 계열 대응 방식 예시'),

    ('2026-06-09', 'TWF', 'tooling',
     '가공 burr 증가와 표면 조도 저하',
     '공구 날끝 마모와 냉각 부족',
     '공구 교체, 쿨런트 노즐 정렬, 절삭유 농도 확인',
     '공구 교체 기준 강화, 절삭유 농도 점검 주기화',
     35, '{"tool_wear":205,"process_temperature":307}', 'sample_history',
     '공구 마모 재발 방지 패턴'),

    ('2026-06-07', 'HDF', 'coolant_system',
     '공정온도 상승 추세와 냉각 효율 저하',
     '쿨런트 필터 막힘과 유량 저하',
     '필터 교체, 펌프 임펠러 청소, 유량 재확인',
     '필터 차압 점검, 쿨런트 유량 기준값 관리',
     45, '{"air_temperature":298,"process_temperature":306,"torque":55}', 'sample_history',
     'heat dissipation failure 계열 사례'),

    ('2026-06-03', 'SAFETY_INTERLOCK', 'guard_interlock',
     '가드 도어 인터록 열림 상태 감지',
     '인터록 스위치 접점 불안정',
     '인터록 스위치 점검, 배선 정리, 작업자 안전 교육',
     '인터록 우회 금지 교육, 안전회로 정기 시험',
     30, '{}', 'sample_history',
     '안전장치 관련 사례'),

    ('2026-05-30', 'HDF', 'coolant_system',
     '쿨런트 유량 저하 경고',
     '필터 오염과 라인 부분 막힘',
     '필터 교체, 라인 플러싱, 유량 센서 확인',
     '쿨런트 유량 저하 알림 기준 조정, 필터 교체 주기 관리',
     25, '{"process_temperature":304}', 'sample_history',
     '냉각 계통 경미 사례'),

    ('2026-05-27', 'TWF', 'tooling',
     '홀 가공 burr 증가, 공구 마모 징후',
     '드릴 공구 마모와 절삭유 공급 불균일',
     '드릴 교체, 홀 가공 조건 재검토, 절삭유 공급 확인',
     '공구 수명 기준 재설정, burr 검사 기준 강화',
     30, '{"tool_wear":190,"torque":46}', 'sample_history',
     'tool wear failure 유사 사례'),

    ('2026-05-22', 'OSF', 'tooling',
     '마모 공구 사용 후 토크 상승',
     '공구 교체 지연과 절삭 부하 누적',
     '공구 교체 및 토크 기준 재설정',
     'tool_wear 임계값 전 선제 교체, 토크 상승 추이 알림',
     35, '{"torque":58,"tool_wear":210}', 'sample_history',
     'overstrain 사례'),

    ('2026-05-18', 'PWF', 'drive_fan',
     '드라이브 팬 속도 저하',
     '팬 회전 불량과 먼지 축적',
     '드라이브 팬 교체, 방열 경로 청소',
     '전장부 팬 점검 주기화, 온도 알람 기준 확인',
     50, '{"air_temperature":299}', 'sample_history',
     'power/drive cooling 관련 사례'),

    ('2026-05-12', 'TWF', 'tooling',
     '공구 수명 말기 품질 편차 증가',
     '공구 마모 누적',
     '공구 교체, 절삭 조건 확인',
     '공구 사용 시간과 tool_wear 기준을 함께 관리',
     20, '{"tool_wear":188,"torque":49}', 'sample_history',
     '경미한 TWF 사전 징후');
