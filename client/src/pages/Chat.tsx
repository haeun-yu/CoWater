import { useState } from 'react';
import { PageCard } from '../components/layout/PageCard';
import { SYSTEM_AGENT_URL } from '../services/api';

export function ChatPage() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Array<{ role: string; content: string }>>([
    { role: 'system', content: '안녕하세요! 작업 지시를 내려주세요.' }
  ]);
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    if (!input.trim()) return;

    // 사용자 메시지 추가
    const userMsg = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      // Backend에 Intent 전송
      const response = await fetch(`${SYSTEM_AGENT_URL}/mission-proposals/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: input })
      });

      if (response.ok) {
        const data = await response.json();
        const proposal = data.proposal;
        const approval = data.approval;
        const assistantMsg = {
          role: 'assistant',
          content: `✅ 작업 제안이 생성되었습니다!\n제목: ${proposal.title}\n목표: ${proposal.goal || '(no goal)'}\n상태: ${proposal.status}\nProposal ID: ${proposal.id || proposal.proposal_id}\nApproval ID: ${approval?.approval_id || '(pending)'}`
        };
        setMessages(prev => [...prev, assistantMsg]);
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: '❌ 작업 처리 중 오류가 발생했습니다.' }]);
      }
    } catch (error) {
      setMessages(prev => [...prev, { role: 'assistant', content: '❌ 서버 연결 오류' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PageCard title="작업 지시 (Chat)">
        <div className="flex flex-col gap-4 h-[500px]">
          <div className="flex-1 overflow-y-auto border border-[#2c5282] rounded p-3 bg-[#0f172a]">
            {messages.map((msg, idx) => (
              <div key={idx} className={`mb-3 ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
                <div className={`inline-block max-w-xs px-3 py-2 rounded ${
                  msg.role === 'user'
                    ? 'bg-[#2c5282] text-white'
                    : 'bg-[#1e3a8a] text-[#8da8b5]'
                }`}>
                  {msg.content}
                </div>
              </div>
            ))}
            {loading && <div className="text-[#8da8b5] italic">처리 중...</div>}
          </div>

          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSend()}
              placeholder="작업을 입력하세요... (예: 기뢰탐지 해줄래?)"
              disabled={loading}
              className="flex-1 px-3 py-2 bg-[#1e3a8a] text-white border border-[#2c5282] rounded outline-none"
            />
            <button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="px-4 py-2 bg-[#2c5282] text-white rounded hover:bg-[#3b69b3] disabled:opacity-50"
            >
              {loading ? '...' : '전송'}
            </button>
          </div>
        </div>
      </PageCard>

      <PageCard title="사용 예시">
        <ul className="space-y-2 text-[#8da8b5]">
          <li>💡 "항만 주변 기뢰 탐지 해줄래?"</li>
          <li>💡 "주요 해역 수심 조사"</li>
          <li>💡 "모든 장비 상태 점검"</li>
          <li>💡 "배터리 20% 이하 장비 복귀"</li>
          <li className="text-[#64748b] mt-4">📋 각 작업은 자동으로 Proposal이 생성됩니다</li>
          <li className="text-[#64748b]">✅ 자연어 처리: LLM 기반</li>
        </ul>
      </PageCard>
    </div>
  );
}

