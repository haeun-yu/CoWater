import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';

type ButtonProps = {
  children: ReactNode;
  to?: string;
  onClick?: () => void;
  className?: string;
};

export function Button({ children, to, onClick, className }: ButtonProps) {
  const base = 'inline-flex items-center justify-center rounded-xl border border-[rgba(120,178,196,0.18)] bg-[rgba(255,255,255,0.02)] px-4 py-2 transition hover:bg-[rgba(91,192,190,0.14)]';

  if (to) {
    return (
      <Link to={to} className={[base, className].filter(Boolean).join(' ')}>
        {children}
      </Link>
    );
  }

  return (
    <button type="button" onClick={onClick} className={[base, className].filter(Boolean).join(' ')}>
      {children}
    </button>
  );
}
