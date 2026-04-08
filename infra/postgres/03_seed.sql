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

-- 플랫폼은 moth-bridge / 시뮬레이터가 최초 보고 시 자동 등록됨
