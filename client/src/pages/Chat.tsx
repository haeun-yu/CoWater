import { PageCard } from '../components/layout/PageCard';

export function ChatPage() {
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PageCard title="Chat">
        <ul className="list-disc space-y-2 pl-5 text-[#8da8b5]">
          <li>"기뢰탐지 해줄래?"</li>
          <li>"배터리 상태 알려줘"</li>
          <li>"10% 이하 장비는 복귀시켜줘"</li>
        </ul>
      </PageCard>
      <PageCard title="Command Flow">
        <p className="text-[#8da8b5]">The UI reflects the docs flow: SYS_INTENT_CLASSIFIED → Proposal → Mission → Task.</p>
      </PageCard>
    </div>
  );
}

