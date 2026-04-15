-- 보고서 테이블
CREATE TABLE IF NOT EXISTS reports (
    report_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    flow_id TEXT NOT NULL,
    alert_ids TEXT[] DEFAULT '{}',
    report_type TEXT DEFAULT 'summary',  -- 'summary' | 'detailed' | 'incident'
    content TEXT NOT NULL,
    summary TEXT,
    ai_model TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reports_flow_id ON reports(flow_id);
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at DESC);

-- 학습된 파라미터 테이블
CREATE TABLE IF NOT EXISTS learning_parameters (
    param_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    param_name TEXT NOT NULL,
    category TEXT NOT NULL,  -- 'detection' | 'analysis' | 'response'
    agent_id TEXT NOT NULL,
    current_value TEXT NOT NULL,  -- JSON string
    previous_value TEXT,
    source_flow_id TEXT,
    effectiveness_score FLOAT DEFAULT 0.5,  -- 0~1
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_learning_params_name ON learning_parameters(param_name);
CREATE INDEX IF NOT EXISTS idx_learning_params_agent ON learning_parameters(agent_id, param_name);
CREATE INDEX IF NOT EXISTS idx_learning_params_updated ON learning_parameters(updated_at DESC);

-- 학습 인사이트 테이블
CREATE TABLE IF NOT EXISTS learning_insights (
    insight_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    flow_id TEXT NOT NULL,
    stage TEXT NOT NULL,  -- 'detection' | 'analysis' | 'response'
    agent_id TEXT NOT NULL,
    param_name TEXT NOT NULL,
    finding TEXT NOT NULL,
    recommended_value TEXT NOT NULL,  -- JSON string
    current_value TEXT NOT NULL,
    confidence FLOAT,  -- 0~1
    implemented BOOLEAN DEFAULT FALSE,
    implementation_date TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_learning_insights_flow ON learning_insights(flow_id);
CREATE INDEX IF NOT EXISTS idx_learning_insights_agent ON learning_insights(agent_id, stage);
CREATE INDEX IF NOT EXISTS idx_learning_insights_implemented ON learning_insights(implemented) WHERE NOT implemented;
CREATE INDEX IF NOT EXISTS idx_learning_insights_created ON learning_insights(created_at DESC);
