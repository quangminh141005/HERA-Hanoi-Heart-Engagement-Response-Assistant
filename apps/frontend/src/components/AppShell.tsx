import { ShieldCheck } from 'lucide-react';
import { ReactNode } from 'react';

export function AppShell({
  children,
  compact = false,
}: {
  children: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={`app-shell${compact ? ' app-shell-compact' : ''}`}>
      <header className="topbar">
        <a className="brand" href={compact ? '/widget/v1' : '/'} aria-label="HERA - trang chính">
          <span className="brand-mark" aria-hidden="true">
            <img src="/icons/hera-agent-192.png" alt="" />
          </span>
          <span>
            <strong>HERA</strong>
            <small>Trợ lý thông tin Bệnh viện Tim Hà Nội</small>
          </span>
        </a>
        <div className="trust-note">
          <ShieldCheck size={18} aria-hidden="true" />
          <span>Không thay thế tư vấn y tế</span>
        </div>
      </header>
      <main className="main-content">{children}</main>
    </div>
  );
}
