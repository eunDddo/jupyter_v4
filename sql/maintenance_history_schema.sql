-- Manufacturing maintenance/history database schema and seed data.
-- Usage:
--   sqlite3 agent_data/maintenance_history.sqlite < sql/maintenance_history_schema.sql

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS maintenance_history (
    id INTEGER PRIMARY KEY,
    machine_id TEXT NOT NULL,
    event_date TEXT NOT NULL,
    work_type TEXT NOT NULL,
    component TEXT NOT NULL,
    action TEXT NOT NULL,
    technician TEXT,
    downtime_min INTEGER DEFAULT 0,
    cost REAL DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS alarm_logs (
    id INTEGER PRIMARY KEY,
    machine_id TEXT NOT NULL,
    event_time TEXT NOT NULL,
    alarm_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    acknowledged INTEGER DEFAULT 0,
    related_component TEXT
);

CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY,
    machine_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    torque REAL,
    rotational_speed REAL,
    air_temperature REAL,
    process_temperature REAL,
    tool_wear REAL
);

CREATE TABLE IF NOT EXISTS failure_incidents (
    id INTEGER PRIMARY KEY,
    machine_id TEXT NOT NULL,
    event_date TEXT NOT NULL,
    failure_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    root_cause TEXT,
    corrective_action TEXT,
    downtime_min INTEGER DEFAULT 0,
    linked_maintenance_id INTEGER,
    FOREIGN KEY (linked_maintenance_id) REFERENCES maintenance_history(id)
);

CREATE INDEX IF NOT EXISTS idx_maintenance_machine_date
    ON maintenance_history(machine_id, event_date);

CREATE INDEX IF NOT EXISTS idx_alarm_machine_time
    ON alarm_logs(machine_id, event_time);

CREATE INDEX IF NOT EXISTS idx_sensor_machine_time
    ON sensor_readings(machine_id, recorded_at);

CREATE INDEX IF NOT EXISTS idx_incident_machine_date
    ON failure_incidents(machine_id, event_date);

INSERT OR REPLACE INTO maintenance_history
    (id, machine_id, event_date, work_type, component, action, technician, downtime_min, cost, notes)
VALUES
    (1, 'M-1001', '2026-06-18', 'corrective', 'spindle_bearing', '스핀들 베어링 진동 증가로 베어링 교체 및 런아웃 재측정', 'Kim', 180, 1250.0, '가공면 채터 감소 확인'),
    (2, 'M-1001', '2026-06-07', 'preventive', 'coolant_system', '쿨런트 필터 교체 및 유량 점검', 'Park', 45, 180.0, '공정온도 상승 추세 완화'),
    (3, 'M-1001', '2026-05-22', 'inspection', 'tooling', '공구 마모 한계 초과 확인, 엔드밀 교체', 'Lee', 35, 90.0, 'tool_wear 210 이상에서 불량률 증가'),
    (4, 'CNC-02', '2026-06-12', 'corrective', 'axis_servo', 'Y축 서보 알람 후 커넥터 재체결 및 파라미터 백업', 'Choi', 95, 420.0, '간헐 알람 재현 안 됨'),
    (5, 'MILL-03', '2026-06-02', 'preventive', 'guard_interlock', '도어 인터록 스위치 동작 점검 및 배선 정리', 'Han', 30, 60.0, '안전장치 우회 금지 교육 병행'),
    (6, 'M-1001', '2026-04-28', 'corrective', 'drive_belt', '주축 벨트 장력 조정 및 마모 벨트 교체', 'Kim', 70, 260.0, '고부하 운전 시 토크 변동 감소'),
    (7, 'M-1001', '2026-06-20', 'inspection', 'spindle', '스핀들 부하 알람 후 베어링 온도와 진동값 점검', 'Seo', 55, 120.0, '고속 회전 조건에서 부하 편차 재확인 필요'),
    (8, 'M-1001', '2026-06-01', 'preventive', 'lubrication', '윤활 라인 압력 점검 및 오일 보충', 'Park', 25, 75.0, '스핀들 소음 저감'),
    (9, 'M-1001', '2026-05-12', 'calibration', 'axis_alignment', 'X/Y축 백래시 측정 및 보정', 'Lee', 80, 210.0, '가공 치수 편차 개선'),
    (10, 'CNC-02', '2026-06-19', 'inspection', 'axis_servo', 'Y축 서보 드라이브 온도 상승 후 엔코더 케이블 점검', 'Choi', 60, 160.0, '커넥터 잠금 상태 재확인'),
    (11, 'CNC-02', '2026-06-01', 'preventive', 'ball_screw', 'Y축 볼스크류 윤활 및 이송 저항 측정', 'Han', 40, 95.0, '반복 위치결정 편차 정상 범위'),
    (12, 'CNC-02', '2026-05-18', 'corrective', 'servo_drive', '서보 드라이브 냉각팬 교체 및 파라미터 백업', 'Choi', 130, 680.0, '팬 회전 불량으로 온도 알람 발생'),
    (13, 'MILL-03', '2026-06-17', 'corrective', 'coolant_pump', '쿨런트 펌프 압력 저하로 임펠러 청소 및 필터 교체', 'Han', 75, 220.0, '절삭부 온도 안정화'),
    (14, 'MILL-03', '2026-05-28', 'inspection', 'guard_interlock', '가드 도어 인터록 스위치 반복 동작 시험', 'Seo', 35, 50.0, '우회 배선 흔적 없음'),
    (15, 'M-2002', '2026-06-16', 'corrective', 'hydraulic_unit', '유압 유닛 누유 부위 씰 교체 및 압력 재설정', 'Kim', 150, 540.0, '압력 변동 폭 감소'),
    (16, 'M-2002', '2026-06-05', 'preventive', 'conveyor_motor', '칩 컨베이어 모터 전류 측정 및 감속기 윤활', 'Park', 45, 130.0, '부하 전류 정상화'),
    (17, 'PRESS-07', '2026-06-14', 'inspection', 'safety_light_curtain', '라이트 커튼 차광 시험 및 비상정지 회로 확인', 'Jung', 50, 80.0, '정지 응답 시간 기준 이내'),
    (18, 'PRESS-07', '2026-05-30', 'corrective', 'clutch_brake', '클러치 브레이크 마모 패드 교체 및 스트로크 보정', 'Jung', 210, 980.0, '브레이크 응답 지연 해소'),
    (19, 'ROBOT-01', '2026-06-11', 'corrective', 'servo_axis', '6축 서보 과전류 알람 후 하네스 고정 및 원점 재설정', 'Oh', 85, 300.0, '케이블 처짐 개선'),
    (20, 'LATHE-04', '2026-06-09', 'preventive', 'chuck_hydraulic', '척 유압 압력 점검 및 필터 교체', 'Lee', 45, 140.0, '클램프 압력 안정'),
    (21, 'LATHE-04', '2026-05-25', 'inspection', 'spindle_belt', '스핀들 벨트 장력 측정 및 풀리 마모 확인', 'Kim', 35, 60.0, '벨트 미세 균열 관찰'),
    (22, 'CNC-05', '2026-06-13', 'corrective', 'coolant_system', '쿨런트 칠러 성능 저하로 냉각수 보충 및 팬 청소', 'Park', 70, 210.0, '공정온도 알람 감소'),
    (23, 'CNC-05', '2026-05-27', 'inspection', 'tooling', '드릴 공구 마모 검사 및 홀 가공 burr 확인', 'Seo', 30, 45.0, '공구 교체 권고'),
    (24, 'M-3003', '2026-06-06', 'preventive', 'motor_bearing', '이송 모터 베어링 소음 점검 및 그리스 보충', 'Oh', 40, 90.0, '소음 레벨 추적 필요');

INSERT OR REPLACE INTO alarm_logs
    (id, machine_id, event_time, alarm_code, severity, message, acknowledged, related_component)
VALUES
    (1, 'M-1001', '2026-06-19 09:12:00', 'SPN-LOAD-H', 'HIGH', '스핀들 부하 상한 초과', 1, 'spindle'),
    (2, 'M-1001', '2026-06-18 15:44:00', 'VIB-CHT-2', 'MEDIUM', '채터 의심 진동 패턴 감지', 1, 'spindle_bearing'),
    (3, 'M-1001', '2026-06-15 11:03:00', 'TEMP-PROC-H', 'MEDIUM', '공정온도 상승 경고', 1, 'coolant_system'),
    (4, 'CNC-02', '2026-06-12 10:20:00', 'SERVO-Y-ALM', 'HIGH', 'Y축 서보 응답 이상', 1, 'axis_servo'),
    (5, 'MILL-03', '2026-06-03 08:40:00', 'SAFE-DOOR', 'HIGH', '가드 도어 인터록 열림', 1, 'guard_interlock'),
    (6, 'M-1001', '2026-06-20 10:18:00', 'SPN-VIB-H', 'HIGH', '스핀들 진동 RMS 기준 초과', 1, 'spindle_bearing'),
    (7, 'M-1001', '2026-06-09 14:02:00', 'TOOL-WEAR-H', 'HIGH', '공구 마모 한계 접근', 1, 'tooling'),
    (8, 'M-1001', '2026-05-30 16:35:00', 'COOL-FLOW-L', 'LOW', '쿨런트 유량 저하 경고', 1, 'coolant_system'),
    (9, 'CNC-02', '2026-06-19 13:25:00', 'SERVO-TEMP-M', 'MEDIUM', 'Y축 서보 드라이브 온도 상승', 0, 'axis_servo'),
    (10, 'CNC-02', '2026-06-01 09:50:00', 'AXIS-FOLLOW-M', 'MEDIUM', 'Y축 추종 오차 증가', 1, 'ball_screw'),
    (11, 'CNC-02', '2026-05-18 17:40:00', 'DRV-FAN-L', 'LOW', '서보 드라이브 팬 속도 저하', 1, 'servo_drive'),
    (12, 'MILL-03', '2026-06-17 12:12:00', 'COOL-PRESS-L', 'MEDIUM', '쿨런트 압력 저하', 1, 'coolant_pump'),
    (13, 'MILL-03', '2026-05-28 07:55:00', 'SAFE-RESET', 'LOW', '인터록 리셋 반복', 1, 'guard_interlock'),
    (14, 'M-2002', '2026-06-16 11:22:00', 'HYD-PRESS-L', 'HIGH', '유압 압력 급락', 1, 'hydraulic_unit'),
    (15, 'M-2002', '2026-06-05 15:03:00', 'CONV-LOAD-M', 'MEDIUM', '칩 컨베이어 부하 상승', 1, 'conveyor_motor'),
    (16, 'PRESS-07', '2026-06-14 09:31:00', 'SAFE-LC-BLOCK', 'HIGH', '라이트 커튼 차광 상태에서 사이클 시작 요청', 1, 'safety_light_curtain'),
    (17, 'PRESS-07', '2026-05-30 18:10:00', 'BRAKE-DELAY-H', 'HIGH', '브레이크 응답 지연', 1, 'clutch_brake'),
    (18, 'ROBOT-01', '2026-06-11 10:05:00', 'AXIS6-OC', 'HIGH', '6축 서보 과전류', 1, 'servo_axis'),
    (19, 'ROBOT-01', '2026-06-07 14:44:00', 'GRIP-AIR-L', 'MEDIUM', '그리퍼 공압 저하', 1, 'gripper_pneumatic'),
    (20, 'LATHE-04', '2026-06-09 08:47:00', 'CHUCK-PRESS-L', 'HIGH', '척 유압 압력 저하', 1, 'chuck_hydraulic'),
    (21, 'LATHE-04', '2026-05-25 15:21:00', 'SPN-BELT-M', 'MEDIUM', '스핀들 벨트 슬립 의심', 1, 'spindle_belt'),
    (22, 'CNC-05', '2026-06-13 11:13:00', 'TEMP-PROC-H', 'MEDIUM', '공정온도 상승 경고', 1, 'coolant_system'),
    (23, 'CNC-05', '2026-05-27 13:32:00', 'TOOL-BURR-M', 'MEDIUM', '홀 가공 burr 증가', 1, 'tooling'),
    (24, 'M-3003', '2026-06-06 16:08:00', 'MTR-BRG-M', 'MEDIUM', '이송 모터 베어링 소음 상승', 0, 'motor_bearing');

INSERT OR REPLACE INTO sensor_readings
    (id, machine_id, recorded_at, torque, rotational_speed, air_temperature, process_temperature, tool_wear)
VALUES
    (1, 'M-1001', '2026-06-19 09:00:00', 62.0, 1320.0, 298.0, 309.0, 215.0),
    (2, 'M-1001', '2026-06-18 14:30:00', 58.0, 1300.0, 300.0, 307.0, 212.0),
    (3, 'M-1001', '2026-06-07 13:10:00', 49.0, 1450.0, 297.0, 302.0, 188.0),
    (4, 'CNC-02', '2026-06-12 10:00:00', 41.0, 1510.0, 296.0, 301.0, 120.0),
    (5, 'MILL-03', '2026-06-03 08:20:00', 35.0, 1600.0, 295.0, 299.0, 80.0),
    (6, 'M-1001', '2026-06-20 10:00:00', 64.0, 1280.0, 299.0, 311.0, 218.0),
    (7, 'M-1001', '2026-06-15 10:00:00', 55.0, 1380.0, 298.0, 306.0, 204.0),
    (8, 'M-1001', '2026-05-30 10:00:00', 47.0, 1480.0, 296.0, 301.0, 176.0),
    (9, 'CNC-02', '2026-06-19 13:00:00', 44.0, 1505.0, 297.0, 303.0, 128.0),
    (10, 'CNC-02', '2026-06-01 09:30:00', 39.0, 1520.0, 296.0, 300.0, 112.0),
    (11, 'CNC-02', '2026-05-18 17:10:00', 46.0, 1490.0, 298.0, 304.0, 135.0),
    (12, 'MILL-03', '2026-06-17 12:00:00', 38.0, 1580.0, 296.0, 304.0, 96.0),
    (13, 'MILL-03', '2026-05-28 08:00:00', 33.0, 1620.0, 295.0, 298.0, 76.0),
    (14, 'M-2002', '2026-06-16 11:00:00', 52.0, 1410.0, 299.0, 305.0, 165.0),
    (15, 'M-2002', '2026-06-05 14:30:00', 48.0, 1455.0, 297.0, 302.0, 150.0),
    (16, 'M-2002', '2026-05-26 10:30:00', 45.0, 1470.0, 296.0, 300.0, 142.0),
    (17, 'PRESS-07', '2026-06-14 09:10:00', 70.0, 620.0, 300.0, 315.0, 92.0),
    (18, 'PRESS-07', '2026-05-30 17:50:00', 73.0, 610.0, 301.0, 317.0, 95.0),
    (19, 'PRESS-07', '2026-05-20 09:20:00', 65.0, 635.0, 298.0, 310.0, 88.0),
    (20, 'ROBOT-01', '2026-06-11 09:50:00', 28.0, 2100.0, 296.0, 300.0, 45.0),
    (21, 'ROBOT-01', '2026-06-07 14:20:00', 24.0, 2120.0, 295.0, 298.0, 40.0),
    (22, 'ROBOT-01', '2026-05-29 11:00:00', 22.0, 2135.0, 295.0, 297.0, 38.0),
    (23, 'LATHE-04', '2026-06-09 08:30:00', 57.0, 1180.0, 299.0, 307.0, 172.0),
    (24, 'LATHE-04', '2026-05-25 15:00:00', 54.0, 1205.0, 298.0, 304.0, 160.0),
    (25, 'LATHE-04', '2026-05-12 13:00:00', 49.0, 1230.0, 296.0, 301.0, 148.0),
    (26, 'CNC-05', '2026-06-13 11:00:00', 46.0, 1550.0, 300.0, 312.0, 190.0),
    (27, 'CNC-05', '2026-05-27 13:00:00', 43.0, 1580.0, 298.0, 306.0, 178.0),
    (28, 'CNC-05', '2026-05-15 10:00:00', 39.0, 1600.0, 297.0, 302.0, 154.0),
    (29, 'M-3003', '2026-06-06 15:50:00', 51.0, 1390.0, 298.0, 303.0, 132.0),
    (30, 'M-3003', '2026-05-24 10:15:00', 47.0, 1425.0, 296.0, 301.0, 124.0);

INSERT OR REPLACE INTO failure_incidents
    (id, machine_id, event_date, failure_type, severity, root_cause, corrective_action, downtime_min, linked_maintenance_id)
VALUES
    (1, 'M-1001', '2026-06-18', 'TWF', 'HIGH', '공구 마모와 스핀들 진동 복합 영향', '공구 교체, 베어링 점검, 절삭 조건 완화', 180, 1),
    (2, 'M-1001', '2026-05-22', 'OSF', 'MEDIUM', '마모 공구 사용으로 토크 상승', '공구 교체 및 토크 기준 재설정', 35, 3),
    (3, 'CNC-02', '2026-06-12', 'PWF', 'HIGH', 'Y축 서보 커넥터 접촉 불량', '커넥터 재체결 및 알람 모니터링', 95, 4),
    (4, 'M-1001', '2026-06-20', 'HDF', 'MEDIUM', '스핀들 부하 상승과 냉각 성능 저하', '베어링 온도 추적, 쿨런트 유량 점검, 절삭 조건 완화', 55, 7),
    (5, 'CNC-02', '2026-06-19', 'PWF', 'MEDIUM', '서보 드라이브 온도 상승과 엔코더 신호 불안정', '엔코더 케이블 고정, 드라이브 팬 상태 확인', 60, 10),
    (6, 'MILL-03', '2026-06-17', 'HDF', 'MEDIUM', '쿨런트 압력 저하로 공정온도 상승', '필터 교체, 펌프 임펠러 청소, 유량 재확인', 75, 13),
    (7, 'MILL-03', '2026-06-03', 'SAFETY_INTERLOCK', 'HIGH', '가드 도어 인터록 열림 상태 감지', '인터록 스위치 점검 및 작업자 안전 교육', 30, 5),
    (8, 'M-2002', '2026-06-16', 'HYDRAULIC_PRESSURE', 'HIGH', '유압 씰 마모로 압력 급락', '씰 교체, 압력 재설정, 누유 재점검', 150, 15),
    (9, 'M-2002', '2026-06-05', 'CONVEYOR_LOAD', 'MEDIUM', '칩 적재와 감속기 윤활 부족', '칩 제거, 감속기 윤활, 모터 전류 추적', 45, 16),
    (10, 'PRESS-07', '2026-05-30', 'BRAKE_DELAY', 'HIGH', '클러치 브레이크 패드 마모', '패드 교체, 스트로크 보정, 정지거리 검증', 210, 18),
    (11, 'ROBOT-01', '2026-06-11', 'SERVO_OVERCURRENT', 'HIGH', '6축 하네스 처짐에 따른 순간 과전류', '하네스 고정, 원점 재설정, 반복 동작 모니터링', 85, 19),
    (12, 'ROBOT-01', '2026-06-07', 'PNEUMATIC_LOW', 'MEDIUM', '그리퍼 공압 라인 미세 누설', '튜브 피팅 교체 및 압력 유지 시험', 40, NULL),
    (13, 'LATHE-04', '2026-06-09', 'CHUCK_PRESSURE', 'HIGH', '척 유압 필터 막힘으로 클램프 압력 저하', '필터 교체, 압력 확인, 공작물 클램프 재검증', 45, 20),
    (14, 'LATHE-04', '2026-05-25', 'SPINDLE_SLIP', 'MEDIUM', '스핀들 벨트 장력 저하와 미세 균열', '벨트 장력 조정 및 교체 계획 수립', 35, 21),
    (15, 'CNC-05', '2026-06-13', 'HDF', 'MEDIUM', '쿨런트 칠러 성능 저하로 공정온도 상승', '냉각수 보충, 팬 청소, 칠러 부하 추적', 70, 22),
    (16, 'CNC-05', '2026-05-27', 'TWF', 'MEDIUM', '드릴 공구 마모로 burr 증가', '공구 교체 기준 강화 및 홀 가공 조건 재검토', 30, 23),
    (17, 'M-3003', '2026-06-06', 'MOTOR_BEARING', 'MEDIUM', '이송 모터 베어링 윤활 부족', '그리스 보충, 소음 레벨 추적, 베어링 교체 계획', 40, 24);
