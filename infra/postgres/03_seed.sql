-- ============================================================
-- Seed: 테스트용 Zone 데이터 (한국 연안 예시)
-- ============================================================

-- 목포 앞바다 권장 항로 (예시 좌표)
INSERT INTO zones (name, zone_type, geometry, rules) VALUES
(
    '목포항 입출항 항로',
    'fairway',
    ST_GeomFromGeoJSON('{
        "type": "Polygon",
        "coordinates": [[
            [126.35, 34.75],
            [126.40, 34.75],
            [126.40, 34.80],
            [126.35, 34.80],
            [126.35, 34.75]
        ]]
    }'),
    '{"speed_limit_knots": 10}'
),
(
    '목포항 금지구역',
    'prohibited',
    ST_GeomFromGeoJSON('{
        "type": "Polygon",
        "coordinates": [[
            [126.37, 34.77],
            [126.39, 34.77],
            [126.39, 34.79],
            [126.37, 34.79],
            [126.37, 34.77]
        ]]
    }'),
    '{"entry_restriction": "all"}'
),
(
    '여수항 앵커리지',
    'anchorage',
    ST_GeomFromGeoJSON('{
        "type": "Polygon",
        "coordinates": [[
            [127.72, 34.72],
            [127.76, 34.72],
            [127.76, 34.75],
            [127.72, 34.75],
            [127.72, 34.72]
        ]]
    }'),
    '{"max_stay_hours": 72}'
),
(
    '제주 서방 주의구역',
    'precautionary',
    ST_GeomFromGeoJSON('{
        "type": "Polygon",
        "coordinates": [[
            [126.10, 33.40],
            [126.30, 33.40],
            [126.30, 33.55],
            [126.10, 33.55],
            [126.10, 33.40]
        ]]
    }'),
    '{"reason": "어업 활동 밀집 구역"}'
);

-- 테스트용 플랫폼 (실제 연결 전 UI 확인용)
INSERT INTO platforms (platform_id, platform_type, name, flag, source_protocol, capabilities, metadata) VALUES
('MMSI-441001000', 'vessel', '코리아마루', 'KR', 'ais',
 ARRAY['position','heading'], '{"imo": "IMO9123456", "call_sign": "HLKA"}'),

('MMSI-441002000', 'vessel', '한라호', 'KR', 'ais',
 ARRAY['position','heading'], '{"imo": "IMO9234567", "call_sign": "HLKB"}'),

('USV-ALPHA-001', 'usv', 'USV Alpha', NULL, 'mavlink',
 ARRAY['position','heading','camera'], '{"model": "WAM-V 16"}'),

('ROV-SURVEY-001', 'rov', 'ROV Survey 01', NULL, 'ros',
 ARRAY['position','depth','camera','arm'], '{"max_depth_m": 300}')
ON CONFLICT (platform_id) DO NOTHING;
