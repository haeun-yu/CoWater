import { NavLink } from 'react-router-dom';
import { useUiStore } from '../../stores/uiStore';
import { Button } from '../ui/button';

export function Shell({ children }: { children: React.ReactNode }) {
  const sidebarOpen = useUiStore((state) => state.sidebarOpen);

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(91,192,190,0.18),transparent_28%),radial-gradient(circle_at_top_right,rgba(125,211,252,0.1),transparent_22%),linear-gradient(160deg,#07131d,#0b1b27)] text-[#e7f4fa]">
      <div className="grid min-h-screen lg:grid-cols-[260px_1fr]">
        {sidebarOpen ? (
          <aside className="border-r border-[rgba(120,178,196,0.18)] bg-[rgba(4,14,22,0.65)] p-5 backdrop-blur-xl">
            <div className="mb-6 flex items-center gap-3">
              <div className="grid h-11 w-11 place-items-center rounded-[14px] bg-gradient-to-br from-[#5bc0be] to-[#7dd3fc] font-extrabold text-[#031018]">
                C
              </div>
              <div>
                <div className="text-[1.05rem] font-bold">CoWater</div>
                <div className="text-sm text-[#8da8b5]">docs-first control plane</div>
              </div>
            </div>

            <nav className="grid gap-2">
              {[
                ['/', 'Dashboard'],
                ['/proposal', 'Proposal'],
                ['/mission', 'Mission'],
                ['/device', 'Device'],
                ['/policy', 'Policy'],
                ['/events', 'Event Log'],
                ['/analytics', 'Analytics'],
                ['/settings', 'Settings'],
                ['/users', 'Users'],
                ['/chat', 'Chat'],
              ].map(([to, label]) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    [
                      'rounded-xl px-4 py-3 text-[#8da8b5] transition',
                      'hover:translate-x-[2px] hover:bg-[rgba(91,192,190,0.14)] hover:text-[#e7f4fa]',
                      isActive ? 'bg-[rgba(91,192,190,0.14)] text-[#e7f4fa]' : '',
                    ].join(' ')
                  }
                >
                  {label}
                </NavLink>
              ))}
            </nav>
          </aside>
        ) : null}

        <main className="min-w-0">
          <header className="flex flex-wrap items-end justify-between gap-4 px-6 py-7 lg:px-7 lg:pb-4">
            <div>
              <p className="text-sm text-[#8da8b5]">Mission control</p>
              <h1 className="mt-1 text-[clamp(1.4rem,2vw,2.2rem)] font-semibold">SYS_INTENT_CLASSIFIED → Proposal → Mission → Task</h1>
            </div>
            <Button to="/chat">Open Chat</Button>
          </header>

          <div className="px-6 pb-7 lg:px-7">{children}</div>
        </main>
      </div>
    </div>
  );
}
