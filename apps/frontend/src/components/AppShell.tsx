import { HeartPulse, ShieldCheck } from 'lucide-react';
import { ReactNode } from 'react';

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/">
          <span className="brand-mark" aria-hidden="true">
            <HeartPulse size={22} />
          </span>
          <span>
            <strong>HERA</strong>
            <small>Hanoi Heart Hospital assistant</small>
          </span>
        </a>
        <div className="trust-note">
          <ShieldCheck size={18} aria-hidden="true" />
          <span>Official-source ready</span>
        </div>
      </header>
      <main className="main-content">{children}</main>
    </div>
  );
}

